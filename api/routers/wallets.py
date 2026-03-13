"""Wallet CRUD + pipeline auto-chain + sync status endpoints.

Endpoints:
  POST   /api/wallets              — create wallet + queue pipeline jobs
  GET    /api/wallets              — list user's wallets with sync_status
  GET    /api/wallets/{id}/status  — pipeline stage progress bar data
  DELETE /api/wallets/{id}         — delete wallet (user isolation enforced)
  POST   /api/wallets/{id}/resync  — queue new pipeline jobs for existing wallet

All endpoints use get_effective_user so accountants can access client wallets.
All DB calls are synchronous psycopg2 wrapped with run_in_threadpool().

Pipeline auto-chain:
  - NEAR chain: full_sync (p=10) + staking_sync (p=8) + lockup_sync (p=7)
  - EVM chains:  evm_full_sync (p=10)
  - classify_transactions and subsequent jobs auto-chain from handlers.

Stage progress bar mapping (from RESEARCH.md):
  full_sync running        => "Indexing"    0-45%
  classify_transactions    => "Classifying" 45-65%
  calculate_acb running    => "Cost Basis"  65-85%
  verify_balances running  => "Verifying"   85-100%
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from api.dependencies import get_effective_user, get_pool_dep
from api.schemas.wallets import JobSummary, SyncStatusResponse, WalletCreate, WalletResponse

router = APIRouter(prefix="/api/wallets", tags=["wallets"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Job types queued per chain on wallet creation / resync
_NEAR_JOBS = [
    ("full_sync", 10),
    ("staking_sync", 8),
    ("lockup_sync", 7),
]

_EVM_JOBS = [
    ("evm_full_sync", 10),
]

# Mapping from job_type -> (stage_name, pct_min, pct_max)
_STAGE_MAP = {
    "full_sync": ("Indexing", 0, 45),
    "staking_sync": ("Indexing", 0, 45),
    "lockup_sync": ("Indexing", 0, 45),
    "evm_full_sync": ("Indexing", 0, 45),
    "classify_transactions": ("Classifying", 45, 65),
    "calculate_acb": ("Cost Basis", 65, 85),
    "verify_balances": ("Verifying", 85, 100),
}

# Priority ordering for pipeline stages (higher = later in pipeline)
_STAGE_PRIORITY = {
    "Indexing": 1,
    "Classifying": 2,
    "Cost Basis": 3,
    "Verifying": 4,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_near_chain(chain: str) -> bool:
    return chain.upper() == "NEAR"


def _jobs_for_chain(chain: str) -> List[tuple]:
    """Return list of (job_type, priority) tuples to queue for the given chain."""
    if _is_near_chain(chain):
        return _NEAR_JOBS
    return _EVM_JOBS


def _compute_stage(jobs: list) -> tuple:
    """Compute current pipeline stage and percentage from job rows.

    jobs: list of (id, wallet_id, job_type, status, progress_fetched, progress_total, error_message)

    Returns (stage_name: str, pct: int, detail: str)
    """
    if not jobs:
        return "Idle", 0, "No jobs"

    # Check if all jobs are completed/failed
    active_statuses = {"queued", "running", "retrying"}
    all_statuses = {row[3] for row in jobs}
    job_types = {row[2] for row in jobs}

    # Determine the highest pipeline stage that has completed
    completed_job_types = {row[2] for row in jobs if row[3] == "completed"}
    active_jobs = [row for row in jobs if row[3] in active_statuses]

    if active_jobs:
        # Find the latest (highest priority) active stage
        best_stage = None
        best_priority = 0
        best_job = None
        for job in active_jobs:
            jtype = job[2]
            stage_info = _STAGE_MAP.get(jtype)
            if stage_info:
                stage_name, pct_min, pct_max = stage_info
                priority = _STAGE_PRIORITY.get(stage_name, 0)
                if priority > best_priority:
                    best_priority = priority
                    best_stage = (stage_name, pct_min, pct_max)
                    best_job = job

        if best_stage:
            stage_name, pct_min, pct_max = best_stage
            # Calculate progress within stage
            if best_job:
                fetched = best_job[4] or 0
                total = best_job[5] or 0
                if total > 0:
                    within = int((fetched / total) * (pct_max - pct_min))
                    pct = min(pct_min + within, pct_max - 1)
                else:
                    pct = pct_min
            else:
                pct = pct_min
            return stage_name, pct, f"{stage_name} in progress"

    # No active jobs — check if any completed
    if "verify_balances" in completed_job_types:
        return "Done", 100, "Pipeline complete"
    if "calculate_acb" in completed_job_types:
        return "Done", 100, "Pipeline complete"
    if completed_job_types:
        return "Done", 100, "Sync complete"

    # All failed?
    if all_statuses == {"failed"}:
        return "Failed", 0, "Pipeline failed"

    return "Idle", 0, "No active jobs"


def _derive_sync_status(jobs: list) -> str:
    """Derive a simple sync_status string from the job list for WalletResponse."""
    active_statuses = {"queued", "running", "retrying"}
    active_jobs = [j for j in jobs if j[3] in active_statuses]
    if active_jobs:
        # Find the most advanced stage
        best_stage = None
        best_priority = 0
        for job in active_jobs:
            jtype = job[2]
            stage_info = _STAGE_MAP.get(jtype)
            if stage_info:
                stage_name = stage_info[0]
                priority = _STAGE_PRIORITY.get(stage_name, 0)
                if priority > best_priority:
                    best_priority = priority
                    best_stage = stage_name
        if best_stage:
            return best_stage.lower().replace(" ", "_")
        return "running"

    completed = {j[2] for j in jobs if j[3] == "completed"}
    if "verify_balances" in completed or "calculate_acb" in completed:
        return "done"
    if completed:
        return "done"
    failed = [j for j in jobs if j[3] == "failed"]
    if failed:
        return "failed"
    return "idle"


# ---------------------------------------------------------------------------
# POST /api/wallets — Create wallet + queue pipeline jobs
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED, response_model=WalletResponse)
async def create_wallet(
    body: WalletCreate,
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Create a wallet for the authenticated user and queue the full pipeline.

    Returns 409 if the (user_id, account_id, chain) combination already exists.
    """
    user_id = user["user_id"]

    def _create(conn):
        cur = conn.cursor()
        try:
            # Insert wallet — ON CONFLICT DO NOTHING, then check if row was inserted
            cur.execute(
                """
                INSERT INTO wallets (user_id, account_id, chain)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, account_id, chain) DO NOTHING
                RETURNING id
                """,
                (user_id, body.account_id, body.chain),
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                return None  # Duplicate

            wallet_id = row[0]

            # Queue pipeline jobs
            jobs = _jobs_for_chain(body.chain)
            for job_type, priority in jobs:
                cur.execute(
                    """
                    INSERT INTO indexing_jobs (wallet_id, user_id, job_type, status, priority)
                    VALUES (%s, %s, %s, 'queued', %s)
                    """,
                    (wallet_id, user_id, job_type, priority),
                )

            conn.commit()
            return wallet_id
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        wallet_id = await run_in_threadpool(_create, conn)
    finally:
        pool.putconn(conn)

    if wallet_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wallet already exists for this user",
        )

    return WalletResponse(
        id=wallet_id,
        account_id=body.account_id,
        chain=body.chain,
        sync_status="queued",
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )


# ---------------------------------------------------------------------------
# GET /api/wallets — List user's wallets with sync_status
# ---------------------------------------------------------------------------


@router.get("", response_model=List[WalletResponse])
async def list_wallets(
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return all wallets for the authenticated user with derived sync_status."""
    user_id = user["user_id"]

    def _list(conn):
        cur = conn.cursor()
        try:
            # Fetch wallets
            cur.execute(
                """
                SELECT id, account_id, chain, created_at
                FROM wallets
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            wallets = cur.fetchall()
            if not wallets:
                return []

            wallet_ids = [w[0] for w in wallets]

            # Fetch all recent jobs for these wallets
            cur.execute(
                """
                SELECT wallet_id, id, job_type, status, progress_fetched, progress_total, error_message
                FROM indexing_jobs
                WHERE wallet_id = ANY(%s) AND user_id = %s
                ORDER BY created_at DESC
                """,
                (wallet_ids, user_id),
            )
            all_jobs = cur.fetchall()
            return wallets, all_jobs
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        result = await run_in_threadpool(_list, conn)
    finally:
        pool.putconn(conn)

    if not result:
        return []

    wallets, all_jobs = result

    # Group jobs by wallet_id
    from collections import defaultdict
    jobs_by_wallet = defaultdict(list)
    for job in all_jobs:
        wallet_id_key = job[0]
        # Normalize to (id, wallet_id, job_type, status, progress_fetched, progress_total, error_message)
        jobs_by_wallet[wallet_id_key].append((job[1], job[0], job[2], job[3], job[4], job[5], job[6]))

    output = []
    for w in wallets:
        wid, account_id, chain, created_at = w
        wallet_jobs = jobs_by_wallet.get(wid, [])
        sync_status = _derive_sync_status(wallet_jobs)
        output.append(
            WalletResponse(
                id=wid,
                account_id=account_id,
                chain=chain,
                sync_status=sync_status,
                created_at=created_at,
            )
        )

    return output


# ---------------------------------------------------------------------------
# GET /api/wallets/{wallet_id}/status — Pipeline stage progress
# ---------------------------------------------------------------------------


@router.get("/{wallet_id}/status", response_model=SyncStatusResponse)
async def get_wallet_status(
    wallet_id: int,
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return pipeline stage progress for a specific wallet."""
    user_id = user["user_id"]

    def _status(conn):
        cur = conn.cursor()
        try:
            # Verify ownership
            cur.execute(
                "SELECT id, user_id FROM wallets WHERE id = %s AND user_id = %s",
                (wallet_id, user_id),
            )
            row = cur.fetchone()
            if row is None:
                return None

            # Fetch all jobs for this wallet
            cur.execute(
                """
                SELECT id, wallet_id, job_type, status, progress_fetched, progress_total, error_message
                FROM indexing_jobs
                WHERE wallet_id = %s AND user_id = %s
                ORDER BY created_at DESC
                """,
                (wallet_id, user_id),
            )
            jobs = cur.fetchall()
            return jobs
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        jobs = await run_in_threadpool(_status, conn)
    finally:
        pool.putconn(conn)

    if jobs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    stage, pct, detail = _compute_stage(jobs)
    job_summaries = [
        JobSummary(
            id=j[0],
            job_type=j[2],
            status=j[3],
            progress_fetched=j[4],
            progress_total=j[5],
        )
        for j in jobs
    ]

    return SyncStatusResponse(
        wallet_id=wallet_id,
        stage=stage,
        pct=pct,
        detail=detail,
        jobs=job_summaries,
    )


# ---------------------------------------------------------------------------
# DELETE /api/wallets/{wallet_id} — Delete wallet
# ---------------------------------------------------------------------------


@router.delete("/{wallet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wallet(
    wallet_id: int,
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Delete a wallet. Only the owning user can delete their wallet."""
    user_id = user["user_id"]

    def _delete(conn):
        cur = conn.cursor()
        try:
            # Verify ownership first
            cur.execute(
                "SELECT id, user_id FROM wallets WHERE id = %s AND user_id = %s",
                (wallet_id, user_id),
            )
            row = cur.fetchone()
            if row is None:
                return False

            cur.execute("DELETE FROM wallets WHERE id = %s AND user_id = %s", (wallet_id, user_id))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        deleted = await run_in_threadpool(_delete, conn)
    finally:
        pool.putconn(conn)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )


# ---------------------------------------------------------------------------
# POST /api/wallets/{wallet_id}/resync — Re-queue pipeline jobs
# ---------------------------------------------------------------------------


@router.post("/{wallet_id}/resync")
async def resync_wallet(
    wallet_id: int,
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Queue new pipeline jobs for an existing wallet (re-index + reclassify + recalc)."""
    user_id = user["user_id"]

    def _resync(conn):
        cur = conn.cursor()
        try:
            # Verify ownership and get chain
            cur.execute(
                "SELECT id, user_id, chain FROM wallets WHERE id = %s AND user_id = %s",
                (wallet_id, user_id),
            )
            row = cur.fetchone()
            if row is None:
                return None

            chain = row[2]
            jobs = _jobs_for_chain(chain)
            queued = []
            for job_type, priority in jobs:
                cur.execute(
                    """
                    INSERT INTO indexing_jobs (wallet_id, user_id, job_type, status, priority)
                    VALUES (%s, %s, %s, 'queued', %s)
                    RETURNING id
                    """,
                    (wallet_id, user_id, job_type, priority),
                )
                job_row = cur.fetchone()
                if job_row:
                    queued.append(job_row[0])

            conn.commit()
            return queued
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        queued = await run_in_threadpool(_resync, conn)
    finally:
        pool.putconn(conn)

    if queued is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    return {"message": "Resync queued", "jobs": queued}
