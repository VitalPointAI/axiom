"""
Axiom Indexer Service — standalone job queue processor.

Polls the PostgreSQL indexing_jobs table for pending work, dispatches to
chain-specific handlers (NearFetcher, etc.), and implements exponential
backoff retry. Designed to run as a long-lived process in Docker.

Usage:
    python -m indexers.service             # run forever
    python -m indexers.service --once      # process one job and exit
    python -m indexers.service --once --dry-run   # print next job and exit
"""

import argparse
import logging
import signal
import sys
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import JOB_POLL_INTERVAL, SYNC_INTERVAL_MINUTES
from indexers.db import get_pool, close_pool
from indexers.near_fetcher import NearFetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


class IndexerService:
    """
    Standalone indexer service with PostgreSQL job queue polling.

    Architecture:
    - Polls indexing_jobs WHERE status IN ('queued','retrying') FOR UPDATE SKIP LOCKED
    - FOR UPDATE SKIP LOCKED ensures safe concurrent use (multi-worker ready)
    - Dispatches to chain-specific handlers via self.handlers dict
    - Exponential backoff on failure: min(300, 5 * 2^attempts) seconds, capped at 5 min
    - Self-healing: retries up to max_attempts (default 100) before marking failed
    - Graceful shutdown: finishes current job on SIGTERM/SIGINT
    """

    def __init__(self):
        self.pool = get_pool(min_conn=2, max_conn=5)
        self.handlers = {
            "near": NearFetcher(self.pool),
        }
        self.running = True

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Signal handler — finish current job then exit cleanly."""
        logger.info("Shutdown signal received (signal %s). Finishing current job...", signum)
        self.running = False

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    def run(self, once: bool = False) -> None:
        """
        Main polling loop.

        Args:
            once: If True, process at most one job then exit. Useful for testing.
        """
        logger.info("Indexer service starting. handlers=%s poll_interval=%ss", list(self.handlers.keys()), JOB_POLL_INTERVAL)

        try:
            while self.running:
                job = self._claim_next_job()

                if job is None:
                    if once:
                        logger.info("No jobs found. Exiting (--once mode).")
                        break

                    # No work right now — check for incremental sync opportunities
                    self.check_incremental_syncs()

                    logger.debug("No jobs. Sleeping %ss...", JOB_POLL_INTERVAL)
                    time.sleep(JOB_POLL_INTERVAL)
                    continue

                # Process the job
                job_id = job["id"]
                chain = job["chain"]
                job_type = job["job_type"]
                wallet_id = job["wallet_id"]

                logger.info(
                    "Processing job id=%s chain=%s type=%s wallet_id=%s attempt=%s",
                    job_id, chain, job_type, wallet_id, job["attempts"],
                )

                try:
                    handler = self.handlers.get(chain)
                    if handler is None:
                        raise ValueError(f"No handler registered for chain '{chain}'")

                    handler.sync_wallet(job)

                    # Success — mark job as completed
                    self._mark_completed(job_id)
                    logger.info("Job %s completed successfully.", job_id)

                except Exception as exc:
                    error_msg = str(exc)
                    logger.error("Job %s failed: %s", job_id, error_msg, exc_info=True)
                    self._mark_failed_or_retry(job, error_msg)

                if once:
                    break

        finally:
            close_pool()
            logger.info("Indexer service stopped.")

    # ------------------------------------------------------------------
    # Job queue operations
    # ------------------------------------------------------------------

    def _claim_next_job(self) -> Optional[dict]:
        """
        Atomically claim the next available job from the queue.

        Uses FOR UPDATE SKIP LOCKED so multiple workers can coexist without
        stepping on each other (multi-worker ready).

        Returns:
            Job row as dict, or None if the queue is empty.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, user_id, wallet_id, job_type, chain, status,
                       priority, cursor, progress_fetched, progress_total,
                       attempts, max_attempts, last_error, created_at
                FROM indexing_jobs
                WHERE status IN ('queued', 'retrying')
                  AND (next_retry_at IS NULL OR next_retry_at <= NOW())
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
            )
            row = cur.fetchone()
            if row is None:
                cur.close()
                conn.rollback()  # Release lock
                return None

            columns = [
                "id", "user_id", "wallet_id", "job_type", "chain", "status",
                "priority", "cursor", "progress_fetched", "progress_total",
                "attempts", "max_attempts", "last_error", "created_at",
            ]
            job = dict(zip(columns, row))

            # Mark job as running and increment attempt counter
            cur.execute(
                """
                UPDATE indexing_jobs
                SET status = 'running',
                    started_at = NOW(),
                    attempts = attempts + 1,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (job["id"],),
            )
            job["attempts"] = job["attempts"] + 1
            conn.commit()
            cur.close()
            return job

        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    def _mark_completed(self, job_id: int) -> None:
        """Mark a job as completed."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE indexing_jobs
                SET status = 'completed',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (job_id,),
            )
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    def _mark_failed_or_retry(self, job: dict, error_msg: str) -> None:
        """
        Mark job for retry with exponential backoff, or as failed if max_attempts reached.

        Backoff formula: min(300, 5 * 2^attempts) seconds (caps at 5 minutes).
        max_attempts defaults to 100 — effectively infinite for real-world scenarios.
        """
        attempts = job["attempts"]
        max_attempts = job["max_attempts"]

        if attempts >= max_attempts:
            new_status = "failed"
            next_retry_at = None
            logger.warning("Job %s exhausted %s attempts. Marking as failed.", job["id"], max_attempts)
        else:
            new_status = "retrying"
            backoff_seconds = min(300, 5 * (2 ** attempts))
            next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
            logger.info(
                "Job %s will retry in %ss (attempt %s/%s).",
                job["id"], backoff_seconds, attempts, max_attempts,
            )

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE indexing_jobs
                SET status = %s,
                    last_error = %s,
                    next_retry_at = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (new_status, error_msg[:2000], next_retry_at, job["id"]),
            )
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Incremental sync scheduling
    # ------------------------------------------------------------------

    def check_incremental_syncs(self) -> None:
        """
        Create incremental_sync jobs for wallets whose last sync has expired.

        Runs after each poll interval when the queue is empty. Queries wallets
        that have at least one completed full_sync job and whose last completed
        sync was more than SYNC_INTERVAL_MINUTES ago. Does not create a new job
        if one is already queued or running for that wallet.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Find wallets needing incremental sync
            cur.execute(
                """
                SELECT w.id AS wallet_id, w.user_id, w.chain,
                       MAX(j.completed_at) AS last_completed,
                       MAX(j.cursor) AS last_cursor
                FROM wallets w
                JOIN indexing_jobs j ON j.wallet_id = w.id
                WHERE j.status = 'completed'
                  AND j.job_type IN ('full_sync', 'incremental_sync')
                GROUP BY w.id, w.user_id, w.chain
                HAVING MAX(j.completed_at) < NOW() - INTERVAL '%s minutes'
                   AND NOT EXISTS (
                       SELECT 1 FROM indexing_jobs pending
                       WHERE pending.wallet_id = w.id
                         AND pending.status IN ('queued', 'running', 'retrying')
                   )
                """,
                (SYNC_INTERVAL_MINUTES,),
            )
            wallets = cur.fetchall()

            for wallet_id, user_id, chain, last_completed, last_cursor in wallets:
                logger.info(
                    "Scheduling incremental sync for wallet_id=%s (last sync: %s)",
                    wallet_id, last_completed,
                )
                cur.execute(
                    """
                    INSERT INTO indexing_jobs
                        (user_id, wallet_id, job_type, chain, status, priority, cursor)
                    VALUES (%s, %s, 'incremental_sync', %s, 'queued', 0, %s)
                    """,
                    (user_id, wallet_id, chain, last_cursor),
                )

            conn.commit()
            cur.close()

        except Exception as e:
            conn.rollback()
            logger.warning("check_incremental_syncs error: %s", e)
        finally:
            self.pool.putconn(conn)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Axiom Indexer Service — processes the PostgreSQL job queue"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one job then exit (useful for testing and smoke checks)",
    )
    args = parser.parse_args()

    service = IndexerService()
    service.run(once=args.once)
