"""
FileImportHandler — processes file_import jobs from the IndexerService queue.

Auto-detects exchange format by trying each registered parser's detect() method,
routes to the correct parser, and updates the file_imports table with results.
"""

import logging
from typing import Optional

from indexers.exchange_parsers.coinbase import CoinbaseParser
from indexers.exchange_parsers.crypto_com import CryptoComParser
from indexers.exchange_parsers.wealthsimple import WealthsimpleParser
from indexers.exchange_parsers.generic import GenericParser
from indexers.ai_file_agent import AIFileAgent

logger = logging.getLogger(__name__)


class FileImportHandler:
    """Processes file_import jobs from the queue.

    Auto-detects exchange format, routes to appropriate parser,
    updates file_imports table with results.

    Registered in IndexerService.handlers as 'file_import'.
    job['cursor'] contains the file_imports.id set by the upload API.
    """

    def __init__(self, pool):
        self.pool = pool
        # Parsers are tried in order; first match wins.
        # GenericParser handles Uphold, Coinsquare, Bitbuy (format-specific detection).
        self.parsers = [
            CoinbaseParser(),
            CryptoComParser(),
            WealthsimpleParser(),
            GenericParser(),
        ]

    def process_file(self, job: dict) -> None:
        """Process a file_import job.

        Args:
            job: dict from IndexerService with at minimum:
                 - cursor: file_imports.id (set by upload API)
                 - user_id: owner of the import
                 - id: indexing_jobs.id

        Steps:
        1. Load file_imports record to get storage_path, user_id
        2. Update status to 'processing'
        3. Read first 5 lines for header detection
        4. Try each parser's detect() method to find the right one
        5. If no parser matches, set status='needs_ai' for AI agent (plan 05)
        6. If parser found, call parser.import_to_db()
        7. Update file_imports with results (rows_imported, rows_skipped, exchange_detected, status)
        """
        file_import_id = job.get("cursor")
        if not file_import_id:
            raise ValueError("file_import job missing cursor (file_imports.id)")

        # Attempt to cast to int — cursor column is TEXT in indexing_jobs
        try:
            file_import_id = int(file_import_id)
        except (TypeError, ValueError):
            raise ValueError(
                f"file_import job cursor is not a valid integer: {file_import_id!r}"
            )

        logger.info(
            "FileImportHandler: processing file_import_id=%s (job_id=%s)",
            file_import_id,
            job.get("id"),
        )

        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # 1. Load the file_imports record
            cur.execute(
                "SELECT id, user_id, filename, storage_path, status FROM file_imports WHERE id = %s",
                (file_import_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"file_imports record not found for id={file_import_id}")

            fi_id, user_id, filename, storage_path, current_status = row

            # 2. Mark as processing
            cur.execute(
                "UPDATE file_imports SET status = 'processing', updated_at = NOW() WHERE id = %s",
                (fi_id,),
            )
            conn.commit()

            # 3. Read first 5 lines for parser detection
            try:
                with open(storage_path, "r", encoding="utf-8-sig") as f:
                    first_lines = f.readlines()[:5]
            except (OSError, IOError) as exc:
                self._set_failed(fi_id, f"Cannot read file: {exc}", conn)
                return

            # 4. Try each parser
            matched_parser = None
            for parser in self.parsers:
                try:
                    if parser.detect(storage_path, first_lines):
                        matched_parser = parser
                        break
                except Exception as exc:
                    logger.warning(
                        "Parser %s detect() raised: %s",
                        parser.exchange_name,
                        exc,
                    )

            # 5. No parser matched — route to AIFileAgent for AI extraction
            if matched_parser is None:
                logger.info(
                    "No parser matched file_import_id=%s (%s) — routing to AIFileAgent",
                    fi_id,
                    filename,
                )
                cur.close()
                # Release connection back to pool before calling AI agent
                # (AI agent manages its own connections; avoids pool exhaustion)
                self.pool.putconn(conn)
                conn = None

                try:
                    ai_result = AIFileAgent(self.pool).process_file(fi_id, user_id)
                except Exception as ai_exc:
                    logger.error(
                        "AIFileAgent failed for file_import_id=%s: %s",
                        fi_id, ai_exc, exc_info=True,
                    )
                    # Re-acquire connection to set failed status
                    conn = self.pool.getconn()
                    self._set_failed(fi_id, f"AI agent error: {ai_exc}", conn)
                    self.pool.putconn(conn)
                    conn = None
                else:
                    logger.info(
                        "AIFileAgent complete for file_import_id=%s: "
                        "imported=%s flagged=%s exchange=%s",
                        fi_id,
                        ai_result.get("imported", 0),
                        ai_result.get("flagged", 0),
                        ai_result.get("exchange_detected"),
                    )
                # AI agent has already updated file_imports status; nothing more to do
                return

            logger.info(
                "Detected exchange=%s for file_import_id=%s (%s)",
                matched_parser.exchange_name,
                fi_id,
                filename,
            )

            # 6. Import via the matched parser
            try:
                result = matched_parser.import_to_db(
                    storage_path,
                    user_id,
                    self.pool,
                    batch_id=f"file_{fi_id}",
                )
            except Exception as exc:
                logger.error(
                    "Parser import_to_db failed for file_import_id=%s: %s",
                    fi_id,
                    exc,
                    exc_info=True,
                )
                self._set_failed(fi_id, str(exc), conn)
                cur.close()
                return

            # 7. Update file_imports with results
            rows_imported = result.get("imported", 0)
            rows_skipped = result.get("skipped", 0)
            rows_flagged = result.get("errors", 0)

            cur.execute(
                """
                UPDATE file_imports
                SET status = 'completed',
                    exchange_detected = %s,
                    rows_imported = %s,
                    rows_skipped = %s,
                    rows_flagged = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    matched_parser.exchange_name,
                    rows_imported,
                    rows_skipped,
                    rows_flagged,
                    fi_id,
                ),
            )
            conn.commit()
            cur.close()

            logger.info(
                "file_import_id=%s complete: exchange=%s imported=%s skipped=%s",
                fi_id,
                matched_parser.exchange_name,
                rows_imported,
                rows_skipped,
            )

        except Exception as exc:
            if conn is not None:
                conn.rollback()
            logger.error(
                "FileImportHandler unhandled error for file_import_id=%s: %s",
                file_import_id,
                exc,
                exc_info=True,
            )
            # Attempt to mark failed; use existing conn or acquire a fresh one
            try:
                if conn is None:
                    conn = self.pool.getconn()
                self._set_failed(file_import_id, str(exc), conn)
            except Exception:
                pass
            raise
        finally:
            if conn is not None:
                self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_failed(self, file_import_id: int, error_message: str, conn) -> None:
        """Update file_imports status to 'failed' with error_message."""
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE file_imports
                SET status = 'failed',
                    error_message = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (error_message[:2000], file_import_id),
            )
            conn.commit()
            cur.close()
        except Exception as exc:
            conn.rollback()
            logger.error("_set_failed failed for file_import_id=%s: %s", file_import_id, exc)
