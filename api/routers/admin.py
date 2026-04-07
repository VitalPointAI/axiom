"""Admin API endpoints for cost dashboard and indexing status.

Endpoints:
  GET /api/admin/cost-summary           — Monthly cost aggregation per chain/provider
  GET /api/admin/indexing-status        — Per-chain sync health
  GET /api/admin/budget-alerts          — Chains exceeding monthly budget
  GET /api/admin/account-indexer-status — Account block index health + progress
  GET /api/admin/containers             — Docker container health and resource usage

All endpoints require admin authentication via require_admin dependency.

Data sources:
  - api_cost_monthly view (migration 011): aggregated cost data
  - chain_sync_config table: enabled chains and budget limits
  - indexing_jobs table: last job status per chain
  - api_cost_log table: last API call timestamp per chain
  - account_indexer_state / account_block_index tables (migration 018)
  - Docker socket (/var/run/docker.sock) for container status
"""

import logging
import subprocess
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


# ---------------------------------------------------------------------------
# GET /api/admin/account-indexer-status
# ---------------------------------------------------------------------------


@router.get("/account-indexer-status")
async def get_account_indexer_status(
    user=Depends(require_admin),
    pool=Depends(get_pool_dep),
):
    """Return account block index health and progress.

    Shows: last processed block, chain tip distance, total index entries,
    unique accounts, staleness, and estimated progress percentage.

    Used by the admin dashboard to monitor the sidecar indexer.

    Returns 'not_initialized' status if migration 018 hasn't been applied yet.
    """

    def _query(conn):
        cur = conn.cursor()
        try:
            # Check if table exists
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'account_indexer_state'
                )
                """
            )
            if not cur.fetchone()[0]:
                return None

            # Get indexer state
            cur.execute(
                "SELECT last_processed_block, updated_at FROM account_indexer_state WHERE id = 1"
            )
            state = cur.fetchone()
            if not state:
                return None

            last_block, updated_at = state

            # Get index stats
            cur.execute("SELECT COUNT(*) FROM account_block_index")
            total_entries = cur.fetchone()[0]

            cur.execute("SELECT COUNT(DISTINCT account_id) FROM account_block_index")
            unique_accounts = cur.fetchone()[0]

            return {
                "last_processed_block": last_block,
                "updated_at": updated_at,
                "total_entries": total_entries,
                "unique_accounts": unique_accounts,
            }
        except Exception as exc:
            logger.debug("account-indexer-status query error: %s", exc)
            return None
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        result = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    if result is None:
        return {
            "status": "not_initialized",
            "message": "Account indexer tables not found. Run migration 018.",
        }

    last_block = result["last_processed_block"]
    updated_at = result["updated_at"]

    # Calculate staleness
    if updated_at:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        stale_seconds = (now - updated_at).total_seconds()
    else:
        stale_seconds = None

    # Estimate progress (NEAR mainnet genesis = 9,820,210, current tip ~180M+)
    genesis = 9_820_210
    # Rough estimate — actual tip comes from neardata, but we don't want to
    # call an external API from this endpoint. Use a reasonable estimate.
    estimated_tip = 185_000_000
    if last_block > genesis:
        progress_pct = min(99.9, ((last_block - genesis) / (estimated_tip - genesis)) * 100)
    else:
        progress_pct = 0.0

    # Determine health status
    if last_block < genesis + 1_000_000:
        status = "building"
    elif stale_seconds is not None and stale_seconds > 300:
        status = "stale"
    elif stale_seconds is not None and stale_seconds > 60:
        status = "lagging"
    else:
        status = "healthy"

    return {
        "status": status,
        "last_processed_block": last_block,
        "progress_pct": round(progress_pct, 1),
        "total_entries": result["total_entries"],
        "unique_accounts": result["unique_accounts"],
        "updated_at": str(updated_at) if updated_at else None,
        "stale_seconds": int(stale_seconds) if stale_seconds is not None else None,
    }


# ---------------------------------------------------------------------------
# GET /api/admin/containers
# ---------------------------------------------------------------------------


@router.get("/containers")
async def get_container_status(
    user=Depends(require_admin),
):
    """Return status, health, uptime, and resource usage for all Axiom containers.

    Uses 'docker ps' and 'docker stats' via subprocess since the API container
    has access to the Docker socket.
    """
    import json as json_mod

    def _get_containers():
        # Get container list with status
        result = subprocess.run(
            [
                "docker", "ps", "-a",
                "--filter", "name=axiom-",
                "--format", '{"name":"{{.Names}}","status":"{{.Status}}","state":"{{.State}}","image":"{{.Image}}"}',
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []

        containers = []
        for line in result.stdout.strip().split("\n"):
            if line:
                try:
                    containers.append(json_mod.loads(line))
                except json_mod.JSONDecodeError:
                    pass

        # Get resource usage for running containers
        stats_result = subprocess.run(
            [
                "docker", "stats", "--no-stream",
                "--filter", "name=axiom-",
                "--format", '{"name":"{{.Name}}","cpu":"{{.CPUPerc}}","mem":"{{.MemUsage}}","mem_pct":"{{.MemPerc}}","net":"{{.NetIO}}"}',
            ],
            capture_output=True, text=True, timeout=15,
        )

        stats_map = {}
        if stats_result.returncode == 0:
            for line in stats_result.stdout.strip().split("\n"):
                if line:
                    try:
                        s = json_mod.loads(line)
                        stats_map[s["name"]] = s
                    except json_mod.JSONDecodeError:
                        pass

        # Get health check status
        health_result = subprocess.run(
            [
                "docker", "inspect",
                "--format", '{{.Name}}\t{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}',
            ] + [c["name"] for c in containers],
            capture_output=True, text=True, timeout=10,
        )

        health_map = {}
        if health_result.returncode == 0:
            for line in health_result.stdout.strip().split("\n"):
                parts = line.strip().split("\t")
                if len(parts) == 2:
                    name = parts[0].lstrip("/")
                    health_map[name] = parts[1]

        # Merge everything
        for c in containers:
            name = c["name"]
            stats = stats_map.get(name, {})
            c["cpu"] = stats.get("cpu", "0%")
            c["mem"] = stats.get("mem", "0B / 0B")
            c["mem_pct"] = stats.get("mem_pct", "0%")
            c["net"] = stats.get("net", "0B / 0B")
            c["health"] = health_map.get(name, "none")

            # Clean up the service name for display
            c["service"] = name.replace("axiom-", "").rstrip("-1").rstrip("-")

        return containers

    try:
        containers = await run_in_threadpool(_get_containers)
    except Exception as exc:
        logger.warning("Failed to get container status: %s", exc)
        return {"error": "Cannot access Docker", "containers": []}

    # Also get host disk and memory info
    def _get_host_stats():
        disk = subprocess.run(
            ["df", "-h", "/"],
            capture_output=True, text=True, timeout=5,
        )
        mem = subprocess.run(
            ["free", "-h"],
            capture_output=True, text=True, timeout=5,
        )
        disk_info = {}
        if disk.returncode == 0:
            lines = disk.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    disk_info = {
                        "total": parts[1],
                        "used": parts[2],
                        "available": parts[3],
                        "use_pct": parts[4],
                    }
        mem_info = {}
        if mem.returncode == 0:
            lines = mem.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 6:
                    mem_info = {
                        "total": parts[1],
                        "used": parts[2],
                        "available": parts[6] if len(parts) > 6 else parts[3],
                    }
        return {"disk": disk_info, "memory": mem_info}

    try:
        host = await run_in_threadpool(_get_host_stats)
    except Exception:
        host = {"disk": {}, "memory": {}}

    return {"containers": containers, "host": host}
