"""VerifyHandler -- job handler for the 'verify_balances' job type.

Registered in IndexerService as 'verify_balances'.
Triggered after calculate_acb completes (queued by ACBHandler).

Orchestrates three verification modules:
  1. verify/reconcile.py -- balance reconciliation
  2. verify/duplicates.py -- duplicate detection
  3. verify/gaps.py -- missing transaction finder
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
          1. Run balance reconciliation for all user wallets
          2. Run duplicate detection scan
          3. Run gap detection
          4. Update account_verification_status rollup

        Args:
            job: Job dict from indexing_jobs row. Must contain 'user_id'.
        """
        user_id = job["user_id"]
        logger.info("Starting verification for user_id=%s", user_id)

        # Phase 5 Plans 02-04 will implement these imports and calls.
        # For now, log placeholder to confirm handler wiring works.

        # Step 1: Balance reconciliation
        logger.info("Step 1: Balance reconciliation for user_id=%s (not yet implemented)", user_id)

        # Step 2: Duplicate detection
        logger.info("Step 2: Duplicate detection for user_id=%s (not yet implemented)", user_id)

        # Step 3: Gap detection
        logger.info("Step 3: Gap detection for user_id=%s (not yet implemented)", user_id)

        # Step 4: Update account verification status rollup
        self._update_account_status(user_id)

        logger.info("Verification complete for user_id=%s", user_id)

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
