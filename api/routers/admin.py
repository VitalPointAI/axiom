"""Admin API endpoints for cost dashboard and indexing status.

Endpoints:
  GET /api/admin/cost-summary    — Monthly cost aggregation per chain/provider
  GET /api/admin/indexing-status — Per-chain sync health
  GET /api/admin/budget-alerts   — Chains exceeding monthly budget

All endpoints require admin authentication via require_admin dependency.

Data sources:
  - api_cost_monthly view (migration 011): aggregated cost data
  - chain_sync_config table: enabled chains and budget limits
  - indexing_jobs table: last job status per chain
  - api_cost_log table: last API call timestamp per chain
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

from api.dependencies import get_pool_dep, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# GET /api/admin/cost-summary
# ---------------------------------------------------------------------------


@router.get("/cost-summary")
async def get_cost_summary(
    chain: Optional[str] = Query(default=None, description="Filter by chain (e.g. 'near', 'ethereum')"),
    user=Depends(require_admin),
    pool=Depends(get_pool_dep),
):
    """Return monthly API cost aggregation from the api_cost_monthly view.

    Each row contains: chain, provider, call_type, month, call_count, total_cost_usd.
    Optional ?chain= query param filters to a specific chain.

    Returns:
        List of cost summary objects.
    """
    def _query(conn):
        cur = conn.cursor()
        try:
            if chain:
                cur.execute(
                    """
                    SELECT chain, provider, call_type, month, call_count, total_cost_usd
                    FROM api_cost_monthly
                    WHERE chain = %s
                    ORDER BY month DESC, chain, provider
                    """,
                    (chain,),
                )
            else:
                cur.execute(
                    """
                    SELECT chain, provider, call_type, month, call_count, total_cost_usd
                    FROM api_cost_monthly
                    ORDER BY month DESC, chain, provider
                    """
                )
            rows = cur.fetchall()
            return rows
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    return [
        {
            "chain": row[0],
            "provider": row[1],
            "call_type": row[2],
            "month": str(row[3]) if row[3] else None,
            "call_count": row[4],
            "total_cost_usd": float(row[5]) if row[5] is not None else 0.0,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# GET /api/admin/indexing-status
# ---------------------------------------------------------------------------


@router.get("/indexing-status")
async def get_indexing_status(
    user=Depends(require_admin),
    pool=Depends(get_pool_dep),
):
    """Return per-chain indexing health from chain_sync_config and indexing_jobs.

    Joins chain_sync_config with the most recent indexing_jobs row per chain
    and the most recent api_cost_log entry per chain.

    Returns:
        List of chain status objects with: chain, enabled, fetcher_class,
        last_job_completed_at, last_job_status, last_api_call_at.
    """
    def _query(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    csc.chain,
                    csc.enabled,
                    csc.fetcher_class,
                    latest_job.completed_at AS last_job_completed_at,
                    latest_job.status AS last_job_status,
                    latest_cost.called_at AS last_api_call_at
                FROM chain_sync_config csc
                LEFT JOIN LATERAL (
                    SELECT ij.updated_at AS completed_at, ij.status
                    FROM indexing_jobs ij
                    JOIN wallets w ON w.id = ij.wallet_id
                    WHERE w.chain = csc.chain
                    ORDER BY ij.updated_at DESC
                    LIMIT 1
                ) latest_job ON true
                LEFT JOIN LATERAL (
                    SELECT acl.created_at AS called_at
                    FROM api_cost_log acl
                    WHERE acl.chain = csc.chain
                    ORDER BY acl.created_at DESC
                    LIMIT 1
                ) latest_cost ON true
                ORDER BY csc.chain
                """
            )
            rows = cur.fetchall()
            return rows
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    return [
        {
            "chain": row[0],
            "enabled": bool(row[1]),
            "fetcher_class": row[2],
            "last_job_completed_at": str(row[3]) if row[3] else None,
            "last_job_status": row[4],
            "last_api_call_at": str(row[5]) if row[5] else None,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# GET /api/admin/budget-alerts
# ---------------------------------------------------------------------------


@router.get("/budget-alerts")
async def get_budget_alerts(
    user=Depends(require_admin),
    pool=Depends(get_pool_dep),
):
    """Return chains where current month's API spend exceeds the monthly budget.

    Queries chain_sync_config for chains with monthly_budget_usd set,
    then compares against current month's total in api_cost_monthly.
    Only returns chains where total > budget.

    Returns:
        List of budget alert objects: chain, monthly_budget_usd, current_spend_usd.
    """
    def _query(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    csc.chain,
                    csc.monthly_budget_usd,
                    COALESCE(SUM(acm.total_cost_usd), 0) AS current_spend_usd
                FROM chain_sync_config csc
                LEFT JOIN api_cost_monthly acm
                    ON acm.chain = csc.chain
                    AND acm.month = date_trunc('month', NOW())
                WHERE csc.monthly_budget_usd IS NOT NULL
                GROUP BY csc.chain, csc.monthly_budget_usd
                HAVING COALESCE(SUM(acm.total_cost_usd), 0) > csc.monthly_budget_usd
                ORDER BY csc.chain
                """
            )
            rows = cur.fetchall()
            return rows
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    return [
        {
            "chain": row[0],
            "monthly_budget_usd": float(row[1]),
            "current_spend_usd": float(row[2]),
        }
        for row in rows
    ]
