"""ACBHandler — job handler for the 'calculate_acb' job type.

Registered in IndexerService as 'calculate_acb'.
Triggered after classify_transactions completes (queued by ClassifierHandler).

Delegates to ACBEngine.calculate_for_user() which:
  1. Clears existing acb_snapshots, capital_gains_ledger, income_ledger for user
  2. Replays all classified transactions chronologically
  3. Writes ACBSnapshot rows per event
  4. Records disposals in capital_gains_ledger
  5. Records income events in income_ledger
  6. Runs SuperficialLossDetector to flag CRA 30-day superficial losses
"""

import logging

logger = logging.getLogger(__name__)


class ACBHandler:
    """Job handler for 'calculate_acb' job type.

    Registered in IndexerService. Triggered after classification completes.

    Args:
        pool: psycopg2 connection pool (has getconn() / putconn())
        price_service: PriceService instance for FMV lookups
    """

    def __init__(self, pool, price_service):
        self.pool = pool
        self.price_service = price_service

    def run_calculate_acb(self, job: dict) -> None:
        """Run ACB calculation for a user.

        Called by IndexerService when job_type == 'calculate_acb'.

        Args:
            job: Job dict from indexing_jobs row. Must contain 'user_id'.
        """
        from engine.acb import ACBEngine

        user_id = job["user_id"]
        logger.info("Starting ACB calculation for user_id=%s", user_id)

        engine = ACBEngine(self.pool, self.price_service)
        stats = engine.calculate_for_user(user_id)

        logger.info(
            "ACB complete for user_id=%s: %d snapshots, %d gains, %d income, "
            "%d tokens, %d superficial losses",
            user_id,
            stats.get("snapshots_written", 0),
            stats.get("gains_recorded", 0),
            stats.get("income_recorded", 0),
            stats.get("tokens_processed", 0),
            stats.get("superficial_losses", 0),
        )

        # Queue verify_balances job now that ACB is complete.
        # Verification is user-scoped; wallet_id satisfies FK only.
        wallet_id = job.get("wallet_id")
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM indexing_jobs WHERE user_id=%s AND job_type='verify_balances' AND status IN ('queued','running')",
                (user_id,),
            )
            if cur.fetchone() is None:
                cur.execute(
                    "INSERT INTO indexing_jobs (user_id, wallet_id, job_type, chain, status, priority) VALUES (%s,%s,'verify_balances','all','queued',4)",
                    (user_id, wallet_id),
                )
                conn.commit()
                logger.info("Queued verify_balances job for user_id=%s", user_id)
            else:
                conn.rollback()
                logger.debug("verify_balances job already queued/running for user_id=%s", user_id)
            cur.close()
        except Exception as exc:
            conn.rollback()
            logger.error("Failed to queue verify_balances for user_id=%s: %s", user_id, exc)
        finally:
            self.pool.putconn(conn)
