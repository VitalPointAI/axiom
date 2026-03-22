"""Job status endpoints with pipeline stage progress.

Endpoints:
  GET  /api/jobs/active           — all running/queued jobs for user with pipeline stage
  POST /api/jobs/notify-when-done — opt in to email notification when indexing completes
  GET  /api/jobs/{id}/status      — single job status with progress

NOTE: /api/jobs/active MUST be registered before /api/jobs/{id}/status to
prevent FastAPI from treating "active" as an integer path parameter.

Pipeline stage mapping (from RESEARCH.md):
  full_sync running        => "Indexing"    0-45%
  classify_transactions    => "Classifying" 45-65%
  calculate_acb running    => "Cost Basis"  65-85%
  verify_balances running  => "Verifying"   85-100%
"""

import logging
import math
import os

import boto3

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from api.dependencies import get_effective_user, get_pool_dep
from api.schemas.jobs import ActiveJobsResponse, JobStatusResponse

logger = logging.getLogger(__name__)

SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "noreply@axiom.tax")
SES_REGION = os.environ.get("SES_REGION", "us-east-1")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3003")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# ---------------------------------------------------------------------------
# Stage mapping (same as wallets router)
# ---------------------------------------------------------------------------

_STAGE_MAP = {
    "full_sync": ("Indexing", 0, 45),
    "incremental_sync": ("Indexing", 0, 45),
    "staking_sync": ("Indexing", 0, 45),
    "lockup_sync": ("Indexing", 0, 45),
    "evm_full_sync": ("Indexing", 0, 45),
    "evm_incremental": ("Indexing", 0, 45),
    "xrp_full_sync": ("Indexing", 0, 45),
    "xrp_incremental": ("Indexing", 0, 45),
    "akash_full_sync": ("Indexing", 0, 45),
    "akash_incremental": ("Indexing", 0, 45),
    "file_import": ("Importing", 0, 45),
    "dedup_scan": ("Classifying", 45, 65),
    "classify_transactions": ("Classifying", 45, 65),
    "calculate_acb": ("Cost Basis", 65, 85),
    "verify_balances": ("Verifying", 85, 100),
    "generate_reports": ("Verifying", 85, 100),
}

_STAGE_PRIORITY = {
    "Importing": 1,
    "Indexing": 1,
    "Classifying": 2,
    "Cost Basis": 3,
    "Verifying": 4,
}


def _estimate_minutes(jobs: list) -> int | None:
    """Estimate remaining minutes based on job count and types.

    Heuristics (based on observed performance):
    - NEAR incremental via neardata.xyz: ~12 min per wallet (10K block scan)
    - EVM sync via Etherscan: ~2 min per wallet
    - Classification/ACB/Verify: ~1 min total
    - Queued jobs run sequentially

    Returns estimated minutes remaining, or None if no jobs.
    """
    if not jobs:
        return None

    total_minutes = 0
    for job in jobs:
        jtype = job[2]
        job_status = job[3]
        fetched = job[4] or 0
        total = job[5] or 0

        if job_status == "completed":
            continue

        if jtype in ("full_sync", "incremental_sync", "staking_sync", "lockup_sync"):
            if total > 0 and fetched > 0:
                # Estimate from actual progress rate
                remaining_blocks = total - fetched
                # ~15 blocks/sec observed rate
                total_minutes += max(1, remaining_blocks // 900)
            else:
                total_minutes += 12  # Default per NEAR wallet
        elif jtype in ("evm_full_sync", "evm_incremental"):
            total_minutes += 2
        elif jtype in ("xrp_full_sync", "xrp_incremental"):
            total_minutes += 3
        elif jtype in ("akash_full_sync", "akash_incremental"):
            total_minutes += 3
        elif jtype in ("dedup_scan", "classify_transactions"):
            total_minutes += 1
        elif jtype == "calculate_acb":
            total_minutes += 1
        elif jtype in ("verify_balances", "generate_reports"):
            total_minutes += 1
        else:
            total_minutes += 2

    return max(1, total_minutes) if total_minutes > 0 else None


def _pipeline_from_jobs(jobs: list) -> tuple:
    """Derive pipeline stage and percentage from a list of active job rows.

    Finds the highest-priority *running* job to determine current stage,
    then aggregates progress across ALL jobs in that stage.

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

    # Find the highest-priority stage
    best_stage = "Idle"
    best_priority = 0
    best_pct_min = 0
    best_pct_max = 0

    for job in candidate_jobs:
        jtype = job[2]
        stage_info = _STAGE_MAP.get(jtype)
        if not stage_info:
            continue
        stage_name, pct_min, pct_max = stage_info
        priority = _STAGE_PRIORITY.get(stage_name, 0)
        if priority > best_priority:
            best_priority = priority
            best_stage = stage_name
            best_pct_min = pct_min
            best_pct_max = pct_max

    if best_stage == "Idle":
        return "Idle", 0

    # Aggregate progress across ALL active jobs in the winning stage
    total_fetched = 0
    total_expected = 0
    has_known_total = False

    for job in jobs:
        jtype = job[2]
        stage_info = _STAGE_MAP.get(jtype)
        if not stage_info or stage_info[0] != best_stage:
            continue
        fetched = job[4] or 0
        total = job[5] or 0
        total_fetched += fetched
        if total > 0:
            total_expected += total
            has_known_total = True

    pct_range = best_pct_max - best_pct_min

    if has_known_total and total_expected > 0:
        within = int((total_fetched / total_expected) * pct_range)
    elif total_fetched > 0:
        # No known total — use logarithmic estimate so progress moves
        # visibly even without a total. Approaches pct_range asymptotically.
        ratio = min(math.log1p(total_fetched) / math.log1p(25000), 0.95)
        within = int(ratio * pct_range)
    else:
        within = 0

    pct = min(best_pct_min + within, best_pct_max - 1)
    return best_stage, pct


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
    est_minutes = _estimate_minutes(rows)

    # If pipeline just finished, check if user wants a completion email
    if not rows:
        _check_and_send_completion_email(pool, user_id)

    jobs = [_active_row_to_job_status(row) for row in rows]

    return ActiveJobsResponse(
        jobs=jobs,
        pipeline_stage=stage,
        pipeline_pct=pct,
        estimated_minutes=est_minutes,
    )


# ---------------------------------------------------------------------------
# POST /api/jobs/notify-when-done — Opt in to email on completion
# ---------------------------------------------------------------------------


@router.post("/notify-when-done")
async def notify_when_done(
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Set notify_on_complete flag so user gets emailed when indexing finishes."""
    user_id = user["user_id"]

    def _update(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE users SET notify_on_complete = TRUE WHERE id = %s",
                (user_id,),
            )
            conn.commit()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        await run_in_threadpool(_update, conn)
    finally:
        pool.putconn(conn)

    return {"ok": True, "message": "You'll receive an email when indexing completes."}


def _check_and_send_completion_email(pool, user_id: int) -> None:
    """Check if user opted in for notification and send email if indexing is done.

    Called from the /active endpoint when no active jobs remain.
    Clears the flag after sending to avoid duplicate emails.
    """
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT email, notify_on_complete FROM users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        cur.close()

        if not row or not row[1] or not row[0]:
            return

        email = row[0]

        # Clear the flag first to prevent duplicates
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET notify_on_complete = FALSE WHERE id = %s",
            (user_id,),
        )
        conn.commit()
        cur.close()

        # Send the email
        try:
            dashboard_url = f"{FRONTEND_URL}/dashboard"
            ses_client = boto3.client("ses", region_name=SES_REGION)
            ses_client.send_email(
                Source=SES_FROM_EMAIL,
                Destination={"ToAddresses": [email]},
                Message={
                    "Subject": {"Data": "Axiom — Your data is ready"},
                    "Body": {
                        "Text": {
                            "Data": (
                                "Your transactions have been indexed, classified, "
                                "and verified. Your dashboard is ready.\n\n"
                                f"View your dashboard: {dashboard_url}"
                            ),
                        },
                        "Html": {
                            "Data": (
                                '<div style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; '
                                'max-width: 480px; margin: 0 auto; padding: 32px 20px;">'
                                '<h2 style="color: #f3f4f6; margin: 0 0 16px;">Your data is ready</h2>'
                                '<p style="color: #9ca3af; line-height: 1.6; margin: 0 0 24px;">'
                                "Axiom has finished indexing your transactions, classifying them, "
                                "calculating cost basis, and verifying balances.</p>"
                                f'<a href="{dashboard_url}" style="display: inline-block; '
                                "background: #2563eb; color: #fff; padding: 12px 24px; "
                                'border-radius: 8px; text-decoration: none; font-weight: 600;">'
                                "View Dashboard</a>"
                                '<p style="color: #6b7280; font-size: 12px; margin-top: 32px;">'
                                "You received this because you opted in to indexing notifications.</p>"
                                "</div>"
                            ),
                        },
                    },
                },
            )
            logger.info("Sent completion email to user_id=%s", user_id)
        except Exception:
            logger.warning("Failed to send completion email to user_id=%s", user_id, exc_info=True)
    except Exception:
        conn.rollback()
        logger.warning("Error checking completion notification for user_id=%s", user_id, exc_info=True)
    finally:
        pool.putconn(conn)


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
