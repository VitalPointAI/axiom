"""API cost tracking and chain registry loading for Axiom indexers.

CostTracker wraps external API calls to record response time and estimated
cost into the api_cost_log table. load_chain_config reads enabled chain
configurations from chain_sync_config.
"""

import logging
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class CostTracker:
    """Track API call costs and check budget alerts.

    Uses the api_cost_log table (migration 011) to record each external API
    call with chain, provider, call_type, response time, and estimated cost.

    Args:
        pool: psycopg2 SimpleConnectionPool instance.
    """

    def __init__(self, pool):
        self.pool = pool

    @contextmanager
    def track(self, chain, provider, call_type, estimated_cost=0.0):
        """Context manager that measures elapsed time and logs to api_cost_log.

        Records the API call even if the wrapped code raises an exception,
        so cost data is never lost.

        Args:
            chain: Chain identifier (e.g. 'near', 'ethereum').
            provider: API provider (e.g. 'neardata_xyz', 'etherscan').
            call_type: Type of call (e.g. 'block_fetch', 'wallet_txns').
            estimated_cost: Estimated USD cost for this call.

        Yields:
            None — use as a plain context manager.
        """
        start = time.monotonic()
        exc_to_raise = None
        try:
            yield
        except Exception as e:
            exc_to_raise = e
        finally:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            try:
                conn = self.pool.getconn()
                try:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO api_cost_log
                            (chain, provider, call_type, response_ms, estimated_cost_usd)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (chain, provider, call_type, elapsed_ms, estimated_cost),
                    )
                    conn.commit()
                    cur.close()
                except Exception:
                    conn.rollback()
                    logger.warning(
                        "Failed to log API cost for %s/%s/%s",
                        chain, provider, call_type,
                        exc_info=True,
                    )
                finally:
                    self.pool.putconn(conn)
            except Exception:
                logger.warning("Could not get connection for cost logging", exc_info=True)

        if exc_to_raise is not None:
            raise exc_to_raise

    def get_monthly_summary(self, chain=None):
        """Query aggregated cost data from the api_cost_monthly view.

        Args:
            chain: Optional chain filter. If None, returns all chains.

        Returns:
            List of tuples: (chain, provider, call_type, month, call_count, total_cost_usd)
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            if chain:
                cur.execute(
                    "SELECT * FROM api_cost_monthly WHERE chain = %s ORDER BY month DESC",
                    (chain,),
                )
            else:
                cur.execute("SELECT * FROM api_cost_monthly ORDER BY month DESC")
            rows = cur.fetchall()
            cur.close()
            return rows
        finally:
            self.pool.putconn(conn)

    def check_budget_alert(self, chain):
        """Check if current month's spend exceeds the chain's monthly budget.

        Args:
            chain: Chain identifier to check.

        Returns:
            True if over budget, False if under or no budget is set.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            # Get budget
            cur.execute(
                "SELECT monthly_budget_usd FROM chain_sync_config WHERE chain = %s",
                (chain,),
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                cur.close()
                return False

            budget = float(row[0])

            # Get current month spend
            cur.execute(
                """
                SELECT COALESCE(SUM(total_cost_usd), 0)
                FROM api_cost_monthly
                WHERE chain = %s
                  AND month = date_trunc('month', NOW())
                """,
                (chain,),
            )
            spend_row = cur.fetchone()
            current_spend = float(spend_row[0]) if spend_row else 0.0
            cur.close()
            return current_spend > budget
        finally:
            self.pool.putconn(conn)


def load_chain_config(pool):
    """Read enabled chain configurations from chain_sync_config.

    Args:
        pool: psycopg2 SimpleConnectionPool instance.

    Returns:
        dict[str, dict] keyed by chain name with keys:
            fetcher_class, job_types, config_json, monthly_budget_usd
    """
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT chain, fetcher_class, job_types, config_json, monthly_budget_usd
            FROM chain_sync_config
            WHERE enabled = true
            """
        )
        rows = cur.fetchall()
        cur.close()

        result = {}
        for chain, fetcher_class, job_types, config_json, monthly_budget in rows:
            result[chain] = {
                "fetcher_class": fetcher_class,
                "job_types": job_types,
                "config_json": config_json,
                "monthly_budget_usd": monthly_budget,
            }
        return result
    finally:
        pool.putconn(conn)
