"""VerifyHandler -- job handler for the 'verify_balances' job type.

Registered in IndexerService as 'verify_balances'.
Triggered after calculate_acb completes (queued by ACBHandler).

Orchestrates four verification modules:
  1. verify/reconcile.py -- balance reconciliation
  2. verify/duplicates.py -- duplicate detection
  3. verify/gaps.py -- missing transaction finder
  4. verify/report.py -- discrepancy report generation
"""
import logging

logger = logging.getLogger(__name__)


class VerifyHandler:
    """Job handler for 'verify_balances' job type.

    Job is user-scoped: wallet_id satisfies FK requirement, but handler
    iterates ALL wallets for user_id (same pattern as ACBHandler).

    Args:
        pool: psycopg2 connection pool
    """

    def __init__(self, pool):
        self.pool = pool

    def run_verify(self, job: dict) -> None:
        """Run full verification suite for a user.

        Called by IndexerService when job_type == 'verify_balances'.

        Steps:
          1. Balance reconciliation (all chains)
          2. Duplicate detection (multi-signal scoring)
          3. Gap detection (NEAR archival RPC)
          4. Account verification status rollup
          5. Discrepancy report generation

        Uses lazy imports to avoid circular imports and to ensure the handler
        skeleton works even before all modules are implemented (same pattern
        as ACBHandler which lazy-imports ACBEngine).

        Args:
            job: Job dict from indexing_jobs row. Must contain 'user_id'.
        """
        from verify.reconcile import BalanceReconciler
        from verify.duplicates import DuplicateDetector
        from verify.gaps import GapDetector
        from verify.report import DiscrepancyReporter

        user_id = job["user_id"]
        logger.info("Starting verification for user_id=%s", user_id)

        # Step 1: Balance reconciliation
        reconciler = BalanceReconciler(self.pool)
        reconcile_stats = reconciler.reconcile_user(user_id)
        logger.info(
            "Reconciliation complete for user_id=%s: %d wallets checked, "
            "%d within tolerance, %d flagged, %d errors",
            user_id,
            reconcile_stats.get("wallets_checked", 0),
            reconcile_stats.get("within_tolerance", 0),
            reconcile_stats.get("flagged", 0),
            reconcile_stats.get("errors", 0),
        )

        # Step 2: Duplicate detection
        detector = DuplicateDetector(self.pool)
        dedup_stats = detector.scan_user(user_id)
        logger.info(
            "Duplicate scan complete for user_id=%s: %d hash dupes merged, "
            "%d bridge flagged, %d exchange flagged/merged",
            user_id,
            dedup_stats.get("hash_dupes_merged", 0),
            dedup_stats.get("bridge_flagged", 0),
            dedup_stats.get("exchange_flagged", 0) + dedup_stats.get("exchange_merged", 0),
        )

        # Step 3: Gap detection (NEAR only)
        gap_detector = GapDetector(self.pool)
        gap_stats = gap_detector.detect_gaps(user_id)
        logger.info(
            "Gap detection complete for user_id=%s: %d wallets scanned, "
            "%d gaps found, %d re-index jobs queued",
            user_id,
            gap_stats.get("wallets_scanned", 0),
            gap_stats.get("gaps_found", 0),
            gap_stats.get("reindex_jobs_queued", 0),
        )

        # Step 4: Update account verification status rollup
        self._update_account_status(user_id)

        # Step 5: Generate discrepancy report
        reporter = DiscrepancyReporter(self.pool)
        report_path = reporter.generate_report(user_id)
        logger.info("Discrepancy report written to %s", report_path)

        logger.info(
            "Verification complete for user_id=%s: "
            "reconciled=%d, dupes=%d, gaps=%d",
            user_id,
            reconcile_stats.get("wallets_checked", 0),
            dedup_stats.get("hash_dupes_merged", 0) + dedup_stats.get("exchange_merged", 0),
            gap_stats.get("gaps_found", 0),
        )

    def _update_account_status(self, user_id: int) -> None:
        """Update account_verification_status for all user wallets.

        For each wallet: count open verification_results. If 0 and at least
        one result exists -> 'verified'. If open_issues > 0 -> 'flagged'.
        If no results -> 'unverified'.

        Uses INSERT ... ON CONFLICT (wallet_id) DO UPDATE for upsert.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()

            # Get all wallets for this user
            cur.execute("SELECT id FROM wallets WHERE user_id = %s", (user_id,))
            wallet_ids = [row[0] for row in cur.fetchall()]

            for wid in wallet_ids:
                # Count open issues
                cur.execute(
                    "SELECT COUNT(*) FROM verification_results WHERE wallet_id = %s AND status = 'open'",
                    (wid,),
                )
                open_count = cur.fetchone()[0]

                # Count total results
                cur.execute(
                    "SELECT COUNT(*) FROM verification_results WHERE wallet_id = %s",
                    (wid,),
                )
                total = cur.fetchone()[0]

                if total == 0:
                    status = "unverified"
                elif open_count > 0:
                    status = "flagged"
                else:
                    status = "verified"

                cur.execute(
                    """
                    INSERT INTO account_verification_status
                        (user_id, wallet_id, status, last_checked_at, open_issues)
                    VALUES (%s, %s, %s, NOW(), %s)
                    ON CONFLICT (wallet_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        last_checked_at = NOW(),
                        open_issues = EXCLUDED.open_issues,
                        updated_at = NOW()
                    """,
                    (user_id, wid, status, open_count),
                )

            conn.commit()
            cur.close()
            logger.info(
                "Updated account_verification_status for user_id=%s (%d wallets)",
                user_id, len(wallet_ids),
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)
