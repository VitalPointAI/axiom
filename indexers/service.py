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

from config import JOB_POLL_INTERVAL, SYNC_INTERVAL_MINUTES, OFFLINE_MODE, NETWORK_JOB_TYPES, NEARBLOCKS_BASE_URL
from indexers.db import get_pool, close_pool
from indexers.near_fetcher import NearFetcher
from indexers.near_stream_fetcher import NearStreamFetcher
from indexers.staking_fetcher import StakingFetcher, _YieldException
from indexers.lockup_fetcher import LockupFetcher
from indexers.price_service import PriceService
from indexers.evm_fetcher import EVMFetcher
from indexers.file_handler import FileImportHandler
from indexers.xrp_fetcher import XRPFetcher
from indexers.akash_fetcher import AkashFetcher
from indexers.dedup_handler import DedupHandler
from indexers.classifier_handler import ClassifierHandler
from indexers.acb_handler import ACBHandler
from indexers.verify_handler import VerifyHandler

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
        self.price_service = PriceService(self.pool)
        self._is_offline: bool = False
        self._offline_reason: str = ""
        self._detect_offline_mode()
        self.handlers = {
            # job_type -> handler mapping
            "full_sync": NearFetcher(self.pool),           # Full transaction history
            "incremental_sync": NearStreamFetcher(self.pool),  # Incremental via neardata.xyz (free)
            "staking_sync": StakingFetcher(self.pool, self.price_service),
            "lockup_sync": LockupFetcher(self.pool, self.price_service),
            "evm_full_sync": EVMFetcher(self.pool),        # EVM full transaction history
            "evm_incremental": EVMFetcher(self.pool),      # EVM incremental tx update
            "file_import": FileImportHandler(self.pool),   # Exchange CSV file import
            # Phase 2 additions
            "xrp_full_sync": XRPFetcher(self.pool),        # XRP Ledger full sync
            "xrp_incremental": XRPFetcher(self.pool),      # XRP Ledger incremental
            "akash_full_sync": AkashFetcher(self.pool),    # Akash Network full sync
            "akash_incremental": AkashFetcher(self.pool),  # Akash Network incremental
            "dedup_scan": DedupHandler(self.pool),         # Cross-source deduplication
            "classify_transactions": ClassifierHandler(self.pool, self.price_service),  # Transaction classification
            "calculate_acb": ACBHandler(self.pool, self.price_service),  # ACB calculation
            "verify_balances": VerifyHandler(self.pool),  # Balance verification
        }
        # Lazy import to avoid circular deps — same pattern as ACBHandler/VerifyHandler
        from reports.handlers.report_handler import ReportHandler
        self.handlers["generate_reports"] = ReportHandler(self.pool)  # priority 3
        self.running = True

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Signal handler — finish current job then exit cleanly."""
        logger.info("Shutdown signal received (signal %s). Finishing current job...", signum)
        self.running = False

    # ------------------------------------------------------------------
    # Offline mode detection
    # ------------------------------------------------------------------

    def _detect_offline_mode(self) -> None:
        """Set self._is_offline based on OFFLINE_MODE config.

        - "true"  → always offline (skip network jobs)
        - "false" → never offline (network failures raise normally)
        - "auto"  → attempt a GET to NEARBLOCKS_BASE_URL with a 3-second
                     timeout; set offline if unreachable.
        """
        if OFFLINE_MODE == "true":
            self._is_offline = True
            self._offline_reason = "OFFLINE_MODE=true"
            logger.info("Offline mode: FORCED (OFFLINE_MODE=true). Network jobs will be re-queued.")
            return

        if OFFLINE_MODE == "false":
            self._is_offline = False
            self._offline_reason = ""
            logger.info("Offline mode: DISABLED (OFFLINE_MODE=false). Network failures will raise.")
            return

        # OFFLINE_MODE == "auto" (default) — probe NearBlocks
        try:
            import requests  # type: ignore
            health_url = f"{NEARBLOCKS_BASE_URL}/health"
            requests.get(health_url, timeout=3)
            self._is_offline = False
            self._offline_reason = ""
            logger.info("Offline mode: auto-check PASSED. NearBlocks reachable.")
        except Exception as exc:
            self._is_offline = True
            self._offline_reason = f"NearBlocks unreachable: {exc}"
            logger.info(
                "Offline mode activated: NearBlocks unreachable (%s). "
                "Network jobs will be re-queued.",
                exc,
            )

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    def _recover_stale_jobs(self) -> int:
        """Reset jobs stuck in 'running' state (orphaned by container restart).

        Any job that has been 'running' for more than 15 minutes without an
        updated_at change is presumed orphaned and reset to 'queued' so the
        indexer can reclaim it. Runs at startup and periodically in the main
        loop.

        Returns the number of recovered jobs.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE indexing_jobs
                SET status = 'queued',
                    started_at = NULL,
                    updated_at = NOW()
                WHERE status = 'running'
                  AND updated_at < NOW() - INTERVAL '15 minutes'
                RETURNING id, job_type
                """,
            )
            recovered = cur.fetchall()
            conn.commit()
            cur.close()
            if recovered:
                for job_id, job_type in recovered:
                    logger.warning("Recovered stale job id=%s type=%s", job_id, job_type)
            return len(recovered)
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    def run(self, once: bool = False) -> None:
        """
        Main polling loop.

        Args:
            once: If True, process at most one job then exit. Useful for testing.
        """
        # Recover any jobs orphaned by previous container restart
        recovered = self._recover_stale_jobs()
        if recovered:
            logger.info("Recovered %d stale running jobs on startup.", recovered)

        logger.info("Indexer service starting. job_types=%s poll_interval=%ss", list(self.handlers.keys()), JOB_POLL_INTERVAL)

        self._last_stale_check = time.time()

        try:
            while self.running:
                # Periodically recover stale jobs (every 60s)
                if time.time() - self._last_stale_check > 60:
                    self._recover_stale_jobs()
                    self._last_stale_check = time.time()

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
                    # Offline mode gate: skip network-dependent jobs when offline.
                    # Move the job back to 'queued' with last_error='offline_mode'.
                    if self._is_offline and job_type in NETWORK_JOB_TYPES:
                        logger.info(
                            "Offline mode: re-queuing job id=%s type=%s (%s)",
                            job_id, job_type, self._offline_reason,
                        )
                        self._requeue_for_offline(job_id)
                        if once:
                            break
                        continue

                    handler = self.handlers.get(job_type)
                    if handler is None:
                        raise ValueError(f"No handler registered for job_type '{job_type}'")

                    # Dispatch to the correct method based on job_type
                    if job_type in ("full_sync", "incremental_sync"):
                        handler.sync_wallet(job)
                    elif job_type == "staking_sync":
                        handler.sync_staking(job)
                    elif job_type == "lockup_sync":
                        handler.sync_lockup(job)
                    elif job_type in ("evm_full_sync", "evm_incremental"):
                        handler.sync_wallet(job)
                    elif job_type == "file_import":
                        handler.process_file(job)
                    elif job_type in ("xrp_full_sync", "xrp_incremental"):
                        handler.sync_wallet(job)
                    elif job_type in ("akash_full_sync", "akash_incremental"):
                        handler.sync_wallet(job)
                    elif job_type == "dedup_scan":
                        handler.run_scan(job)
                    elif job_type == "classify_transactions":
                        handler.run_classify(job)
                    elif job_type == "calculate_acb":
                        handler.run_calculate_acb(job)
                    elif job_type == "verify_balances":
                        handler.run_verify(job)
                    elif job_type == "generate_reports":
                        handler.run(job, conn=None)
                    else:
                        raise ValueError(f"Unknown job_type '{job_type}' — no dispatch method")

                    # Success — mark job as completed
                    self._mark_completed(job_id)
                    logger.info("Job %s completed successfully.", job_id)

                except _YieldException:
                    # Long-running job yielded to let other jobs run — requeue immediately
                    logger.info("Job %s yielded, requeueing.", job_id)
                    self._requeue_job(job_id)

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
                SELECT ij.id, ij.user_id, ij.wallet_id, ij.job_type, ij.chain, ij.status,
                       ij.priority, ij.cursor, ij.progress_fetched, ij.progress_total,
                       ij.attempts, ij.max_attempts, ij.last_error, ij.created_at,
                       w.account_id
                FROM indexing_jobs ij
                JOIN wallets w ON ij.wallet_id = w.id
                WHERE ij.status IN ('queued', 'retrying')
                  AND (ij.next_retry_at IS NULL OR ij.next_retry_at <= NOW())
                  -- Defer staking/lockup until no full_sync jobs remain for same user
                  AND NOT (
                      ij.job_type IN ('staking_sync', 'lockup_sync')
                      AND EXISTS (
                          SELECT 1 FROM indexing_jobs other
                          WHERE other.user_id = ij.user_id
                            AND other.job_type IN ('full_sync', 'incremental_sync')
                            AND other.status IN ('queued', 'running', 'retrying')
                      )
                  )
                ORDER BY ij.priority DESC, ij.created_at ASC
                LIMIT 1
                FOR UPDATE OF ij SKIP LOCKED
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
                "account_id",
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

    def _requeue_job(self, job_id: int) -> None:
        """Requeue a job that yielded, so other higher-priority jobs can run first."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE indexing_jobs
                SET status = 'queued',
                    started_at = NULL,
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

    def _requeue_for_offline(self, job_id: int) -> None:
        """Move a network job back to 'queued' with last_error='offline_mode'.

        This preserves the job for processing once connectivity is restored,
        without consuming an attempt or applying backoff.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE indexing_jobs
                SET status = 'queued',
                    last_error = 'offline_mode',
                    attempts = GREATEST(0, attempts - 1),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (job_id,),
            )
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
            logger.warning("Failed to re-queue job %s for offline mode", job_id)
        finally:
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Incremental sync scheduling
    # ------------------------------------------------------------------

    def check_incremental_syncs(self) -> None:
        """
        Create incremental_sync jobs for wallets whose last sync has expired, and
        periodic staking_sync jobs for NEAR wallets every STAKING_SYNC_INTERVAL_MINUTES.

        Runs after each poll interval when the queue is empty. Queries wallets
        that have at least one completed full_sync job and whose last completed
        sync was more than SYNC_INTERVAL_MINUTES ago. Does not create a new job
        if one is already queued or running for that wallet.

        Staking sync runs on a separate (longer) schedule: hourly by default.
        """
        # Staking runs 4x less often than transaction incremental syncs (e.g. hourly vs 15-min)
        STAKING_SYNC_INTERVAL_MINUTES = SYNC_INTERVAL_MINUTES * 4

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Find USERS needing incremental sync (one job per user, not per wallet).
            # For NEAR, NearStreamFetcher scans blocks for all wallets at once.
            # For other chains, create per-wallet jobs as before.
            cur.execute(
                """
                SELECT DISTINCT w.user_id, w.chain,
                       (SELECT MIN(ww.id) FROM wallets ww WHERE ww.user_id = w.user_id AND ww.chain = w.chain) AS any_wallet_id,
                       MAX(j.completed_at) AS last_completed,
                       MAX(j.cursor) AS last_cursor
                FROM wallets w
                JOIN indexing_jobs j ON j.wallet_id = w.id
                WHERE j.status = 'completed'
                  AND j.job_type IN ('full_sync', 'incremental_sync')
                GROUP BY w.user_id, w.chain
                HAVING MAX(j.completed_at) < NOW() - INTERVAL '%s minutes'
                   AND NOT EXISTS (
                       SELECT 1 FROM indexing_jobs pending
                       WHERE pending.user_id = w.user_id
                         AND pending.job_type = 'incremental_sync'
                         AND pending.status IN ('queued', 'running', 'retrying')
                         AND (SELECT chain FROM wallets ww WHERE ww.id = pending.wallet_id LIMIT 1) = w.chain
                   )
                """,
                (SYNC_INTERVAL_MINUTES,),
            )
            sync_groups = cur.fetchall()

            for user_id, chain, any_wallet_id, last_completed, last_cursor in sync_groups:
                logger.info(
                    "Scheduling incremental sync for user_id=%s chain=%s (last sync: %s)",
                    user_id, chain, last_completed,
                )
                cur.execute(
                    """
                    INSERT INTO indexing_jobs
                        (user_id, wallet_id, job_type, chain, status, priority, cursor)
                    VALUES (%s, %s, 'incremental_sync', %s, 'queued', 0, %s)
                    """,
                    (user_id, any_wallet_id, chain, last_cursor),
                )

            # Find NEAR wallets needing periodic staking sync (hourly)
            cur.execute(
                """
                SELECT w.id AS wallet_id, w.user_id, w.chain,
                       MAX(j.completed_at) AS last_staking_sync
                FROM wallets w
                JOIN indexing_jobs j ON j.wallet_id = w.id
                WHERE j.status = 'completed'
                  AND j.job_type IN ('full_sync', 'staking_sync')
                  AND w.chain = 'near'
                GROUP BY w.id, w.user_id, w.chain
                HAVING MAX(j.completed_at) < NOW() - INTERVAL '%s minutes'
                   AND NOT EXISTS (
                       SELECT 1 FROM indexing_jobs pending
                       WHERE pending.wallet_id = w.id
                         AND pending.job_type = 'staking_sync'
                         AND pending.status IN ('queued', 'running', 'retrying')
                   )
                """,
                (STAKING_SYNC_INTERVAL_MINUTES,),
            )
            staking_wallets = cur.fetchall()

            for wallet_id, user_id, chain, last_staking_sync in staking_wallets:
                logger.info(
                    "Scheduling periodic staking sync for wallet_id=%s (last: %s)",
                    wallet_id, last_staking_sync,
                )
                cur.execute(
                    """
                    INSERT INTO indexing_jobs
                        (user_id, wallet_id, job_type, chain, status, priority)
                    VALUES (%s, %s, 'staking_sync', 'near', 'queued', 2)
                    """,
                    (user_id, wallet_id),
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
    parser.add_argument(
        "--streaming",
        action="store_true",
        help="Launch streaming worker alongside job queue for real-time block monitoring",
    )
    args = parser.parse_args()

    service = IndexerService()

    if args.streaming:
        import asyncio
        import threading
        from indexers.streaming_worker import run_streaming_worker

        def _run_streaming():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_streaming_worker(service.pool))
            except Exception:
                logger.error("Streaming worker crashed", exc_info=True)
            finally:
                loop.close()

        streaming_thread = threading.Thread(target=_run_streaming, daemon=True)
        streaming_thread.start()
        logger.info("Streaming worker launched in background thread")

    service.run(once=args.once)
