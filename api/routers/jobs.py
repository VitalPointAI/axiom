"""Job status endpoints with pipeline stage progress.

Endpoints:
  GET /api/jobs/active          — all running/queued jobs for user with pipeline stage
  GET /api/jobs/{id}/status     — single job status with progress

NOTE: /api/jobs/active MUST be registered before /api/jobs/{id}/status to
prevent FastAPI from treating "active" as an integer path parameter.

Pipeline stage mapping (from RESEARCH.md):
  full_sync running        => "Indexing"    0-45%
  classify_transactions    => "Classifying" 45-65%
  calculate_acb running    => "Cost Basis"  65-85%
  verify_balances running  => "Verifying"   85-100%
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from api.dependencies import get_effective_user, get_pool_dep
from api.schemas.jobs import ActiveJobsResponse, JobStatusResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# ---------------------------------------------------------------------------
# Stage mapping (same as wallets router)
# ---------------------------------------------------------------------------

_STAGE_MAP = {
    "full_sync": ("Indexing", 0, 45),
    "staking_sync": ("Indexing", 0, 45),
    "lockup_sync": ("Indexing", 0, 45),
    "evm_full_sync": ("Indexing", 0, 45),
    "file_import": ("Importing", 0, 45),
    "classify_transactions": ("Classifying", 45, 65),
    "calculate_acb": ("Cost Basis", 65, 85),
    "verify_balances": ("Verifying", 85, 100),
}

_STAGE_PRIORITY = {
    "Importing": 1,
    "Indexing": 1,
    "Classifying": 2,
    "Cost Basis": 3,
    "Verifying": 4,
}


def _pipeline_from_jobs(jobs: list) -> tuple:
    """Derive pipeline stage and percentage from a list of active job rows.

    Finds the highest-priority *running* job to determine current stage.
    Falls back to highest-priority queued/retrying job if nothing is running.

    jobs: list of (id, wallet_id, job_type, status, progress_fetched, progress_total, ...)

    Returns (stage_name: str, pct: int)
    """
    if not jobs:
        return "Idle", 0

    # Prefer running jobs over queued/retrying for stage determination
    running_jobs = [j for j in jobs if j[3] == "running"]
    candidate_jobs = running_jobs if running_jobs else [j for j in jobs if j[3] in ("queued", "retrying")]

    if not candidate_jobs:
        return "Idle", 0

    best_stage = "Idle"
    best_priority = 0
    best_pct = 0

    for job in candidate_jobs:
        jtype = job[2]
        stage_info = _STAGE_MAP.get(jtype)
        if not stage_info:
            continue
        stage_name, pct_min, pct_max = stage_info
        priority = _STAGE_PRIORITY.get(stage_name, 0)
        if priority > best_priority:
            best_priority = priority
            fetched = job[4] or 0
            total = job[5] or 0
            if total > 0:
                within = int((fetched / total) * (pct_max - pct_min))
                pct = min(pct_min + within, pct_max - 1)
            else:
                pct = pct_min
            best_stage = stage_name
            best_pct = pct

    return best_stage, best_pct


def _row_to_job_status(row: tuple) -> JobStatusResponse:
    """Convert a DB row tuple to JobStatusResponse.

    Row (single job query, 8 cols):
      (id, job_type, status, progress_fetched, progress_total, error_message, started_at, completed_at)
    """
    return JobStatusResponse(
        id=row[0],
        job_type=row[1],
        status=row[2],
        progress_fetched=row[3],
        progress_total=row[4],
        error_message=row[5],
        started_at=row[6],
        completed_at=row[7],
    )


def _active_row_to_job_status(row: tuple) -> JobStatusResponse:
    """Convert an active-jobs DB row (9 cols, includes wallet_id) to JobStatusResponse.

    Row (active jobs query, 9 cols):
      (id, wallet_id, job_type, status, progress_fetched, progress_total, error_message, started_at, completed_at)
    """
    return JobStatusResponse(
        id=row[0],
        job_type=row[2],
        status=row[3],
        progress_fetched=row[4],
        progress_total=row[5],
        error_message=row[6],
        started_at=row[7],
        completed_at=row[8],
    )


# ---------------------------------------------------------------------------
# GET /api/jobs/active — MUST be before /{id}/status to avoid param collision
# ---------------------------------------------------------------------------


@router.get("/active", response_model=ActiveJobsResponse)
async def get_active_jobs(
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return all active (queued/running/retrying) jobs for the user.

    Also computes the current pipeline stage and percentage for the progress bar.
    """
    user_id = user["user_id"]

    def _query(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    id,
                    wallet_id,
                    job_type,
                    status,
                    progress_fetched,
                    progress_total,
                    error_message,
                    started_at,
                    completed_at
                FROM indexing_jobs
                WHERE user_id = %s
                  AND status IN ('queued', 'running', 'retrying')
                ORDER BY priority DESC, created_at
                """,
                (user_id,),
            )
            return cur.fetchall()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    stage, pct = _pipeline_from_jobs(rows)

    jobs = [_active_row_to_job_status(row) for row in rows]

    return ActiveJobsResponse(
        jobs=jobs,
        pipeline_stage=stage,
        pipeline_pct=pct,
    )


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/status — Single job status
# ---------------------------------------------------------------------------


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: int,
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return status, progress, and error for a single job.

    Returns 404 if job not found or owned by another user.
    """
    user_id = user["user_id"]

    def _query(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    id,
                    job_type,
                    status,
                    progress_fetched,
                    progress_total,
                    error_message,
                    started_at,
                    completed_at
                FROM indexing_jobs
                WHERE id = %s AND user_id = %s
                """,
                (job_id, user_id),
            )
            return cur.fetchone()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        row = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return _row_to_job_status(row)


# ---------------------------------------------------------------------------
# Stub GET "" for unauthenticated 401 guard
# ---------------------------------------------------------------------------


@router.get("")
async def list_jobs_stub(user=Depends(get_effective_user)):
    """Stub root endpoint — enforces auth so unauthenticated returns 401."""
    return []
