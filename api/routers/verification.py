"""Verification dashboard endpoints.

Endpoints:
  GET  /api/verification/summary          — issue counts grouped by diagnosis_category
  GET  /api/verification/issues           — detailed issues (filter by ?category=...)
  POST /api/verification/resolve/{id}     — mark issue resolved
  POST /api/verification/resync/{id}      — queue re-sync job for affected wallet
  GET  /api/verification/needs-review-count — total unresolved count across tables

Verification results surface data quality issues before reports are generated.
Issues are grouped by diagnosis_category with severity and suggested actions.
User isolation is enforced: only issues for the authenticated user's wallets
are returned.
"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool

from api.dependencies import get_effective_user, get_pool_dep
from db.audit import write_audit
from api.schemas.verification import (
    IssueGroup,
    NeedsReviewCountResponse,
    ResolveRequest,
    VerificationIssue,
    VerificationSummary,
)

router = APIRouter(prefix="/api/verification", tags=["verification"])

# ---------------------------------------------------------------------------
# Category metadata: maps diagnosis_category -> (severity, description, suggested_action)
# ---------------------------------------------------------------------------

_CATEGORY_META = {
    "missing_staking_rewards": (
        "high",
        "Staking rewards not found in indexed data",
        "Re-sync staking rewards",
    ),
    "uncounted_fees": (
        "medium",
        "Transaction fees may not be fully accounted for",
        "Review fee calculations",
    ),
    "unindexed_period": (
        "high",
        "Gap detected in indexed transaction history",
        "Re-index wallet for missing period",
    ),
    "classification_error": (
        "medium",
        "Transaction classification confidence is low",
        "Review transaction classifications",
    ),
    "duplicates": (
        "low",
        "Potential duplicate transactions detected",
        "Review potential duplicate transactions",
    ),
}


# ---------------------------------------------------------------------------
# GET /api/verification/summary
# ---------------------------------------------------------------------------


@router.get("/summary", response_model=VerificationSummary)
async def get_verification_summary(
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return verification issue counts grouped by diagnosis_category.

    Only includes issues for the authenticated user's wallets.
    Also counts needs_review rows in transaction_classifications and capital_gains_ledger.
    """
    user_id = user["user_id"]

    def _query(conn):
        cur = conn.cursor()
        try:
            # Counts per diagnosis_category in verification_results for user's wallets
            cur.execute(
                """
                SELECT
                    vr.diagnosis_category,
                    COUNT(*) AS cnt
                FROM verification_results vr
                JOIN wallets w ON w.id = vr.wallet_id
                WHERE w.user_id = %s
                  AND vr.needs_review = TRUE
                GROUP BY vr.diagnosis_category
                ORDER BY cnt DESC
                """,
                (user_id,),
            )
            category_rows = cur.fetchall()

            # needs_review count in transaction_classifications
            cur.execute(
                """
                SELECT COUNT(*) FROM transaction_classifications tc
                JOIN wallets w ON w.id = tc.wallet_id
                WHERE w.user_id = %s AND tc.needs_review = TRUE
                """,
                (user_id,),
            )
            tc_count = (cur.fetchone() or (0,))[0]

            # needs_review count in capital_gains_ledger
            cur.execute(
                """
                SELECT COUNT(*) FROM capital_gains_ledger
                WHERE user_id = %s AND needs_review = TRUE
                """,
                (user_id,),
            )
            cg_count = (cur.fetchone() or (0,))[0]

            return category_rows, int(tc_count), int(cg_count)
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        category_rows, tc_count, cg_count = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    groups = []
    total = 0
    for row in category_rows:
        cat, cnt = row[0], int(row[1])
        meta = _CATEGORY_META.get(
            cat,
            ("low", f"Issues in category: {cat}", "Review flagged items"),
        )
        severity, description, suggested_action = meta
        groups.append(
            IssueGroup(
                category=cat or "unknown",
                count=cnt,
                severity=severity,
                description=description,
                suggested_action=suggested_action,
            )
        )
        total += cnt

    needs_review_count = total + tc_count + cg_count

    return VerificationSummary(
        groups=groups,
        total_issues=total,
        needs_review_count=needs_review_count,
    )


# ---------------------------------------------------------------------------
# GET /api/verification/issues
# ---------------------------------------------------------------------------


@router.get("/issues", response_model=List[VerificationIssue])
async def get_verification_issues(
    category: Optional[str] = Query(default=None),
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return detailed verification issues for the user's wallets.

    Optional ?category= filter to narrow by diagnosis_category.
    Returns wallet account_id via JOIN.
    """
    user_id = user["user_id"]

    def _query(conn):
        cur = conn.cursor()
        try:
            if category:
                cur.execute(
                    """
                    SELECT
                        vr.id,
                        vr.wallet_id,
                        w.account_id,
                        vr.token_symbol,
                        vr.verification_type,
                        vr.status,
                        vr.expected_balance::text,
                        vr.actual_balance::text,
                        vr.discrepancy::text,
                        vr.diagnosis_category,
                        vr.diagnosis_detail,
                        vr.needs_review,
                        vr.created_at::text
                    FROM verification_results vr
                    JOIN wallets w ON w.id = vr.wallet_id
                    WHERE w.user_id = %s
                      AND vr.diagnosis_category = %s
                    ORDER BY vr.created_at DESC
                    """,
                    (user_id, category),
                )
            else:
                cur.execute(
                    """
                    SELECT
                        vr.id,
                        vr.wallet_id,
                        w.account_id,
                        vr.token_symbol,
                        vr.verification_type,
                        vr.status,
                        vr.expected_balance::text,
                        vr.actual_balance::text,
                        vr.discrepancy::text,
                        vr.diagnosis_category,
                        vr.diagnosis_detail,
                        vr.needs_review,
                        vr.created_at::text
                    FROM verification_results vr
                    JOIN wallets w ON w.id = vr.wallet_id
                    WHERE w.user_id = %s
                    ORDER BY vr.created_at DESC
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

    result = []
    for row in rows:
        (
            issue_id, wallet_id, account_id, token_symbol, verification_type,
            issue_status, expected_balance, actual_balance, discrepancy,
            diagnosis_category, diagnosis_detail, needs_review, created_at,
        ) = row
        # diagnosis_detail may be a dict (psycopg2 JSONB auto-parse) or None
        if isinstance(diagnosis_detail, str):
            try:
                diagnosis_detail = json.loads(diagnosis_detail)
            except (ValueError, TypeError):
                diagnosis_detail = None
        result.append(
            VerificationIssue(
                id=issue_id,
                wallet_id=wallet_id,
                account_id=account_id,
                token_symbol=token_symbol,
                verification_type=verification_type,
                status=issue_status,
                expected_balance=expected_balance,
                actual_balance=actual_balance,
                discrepancy=discrepancy,
                diagnosis_category=diagnosis_category,
                diagnosis_detail=diagnosis_detail,
                needs_review=bool(needs_review),
                created_at=str(created_at) if created_at else "",
            )
        )
    return result


# ---------------------------------------------------------------------------
# POST /api/verification/resolve/{id}
# ---------------------------------------------------------------------------


@router.post("/resolve/{issue_id}")
async def resolve_verification_issue(
    issue_id: int,
    body: ResolveRequest,
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Mark a verification issue as resolved.

    Verifies the issue belongs to the user's wallet before updating.
    Sets needs_review=False and status='resolved'.
    """
    user_id = user["user_id"]

    def _resolve(conn):
        cur = conn.cursor()
        try:
            # Verify ownership and fetch info for audit row
            cur.execute(
                """
                SELECT vr.id, vr.diagnosis_category, vr.verification_type
                FROM verification_results vr
                JOIN wallets w ON w.id = vr.wallet_id
                WHERE vr.id = %s AND w.user_id = %s
                """,
                (issue_id, user_id),
            )
            row = cur.fetchone()
            if row is None:
                return False

            _vr_id, diagnosis_category, verification_type = row

            cur.execute(
                """
                UPDATE verification_results
                SET needs_review = FALSE, status = 'resolved'
                WHERE id = %s
                """,
                (issue_id,),
            )

            # Audit the manual resolution
            write_audit(
                conn,
                user_id=user_id,
                entity_type="verification_result",
                entity_id=issue_id,
                action="verification_resolved",
                new_value={
                    "status": "resolved",
                    "diagnosis_category": diagnosis_category,
                    "verification_type": verification_type,
                },
                actor_type="user",
                notes=body.resolution_notes if hasattr(body, "resolution_notes") else None,
            )

            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        found = await run_in_threadpool(_resolve, conn)
    finally:
        pool.putconn(conn)

    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verification issue not found",
        )

    return {"message": "Issue resolved", "id": issue_id}


# ---------------------------------------------------------------------------
# POST /api/verification/resync/{id}
# ---------------------------------------------------------------------------

# Maps diagnosis_category -> job_type to queue for re-sync
_RESYNC_JOB_MAP = {
    "missing_staking_rewards": "staking_sync",
    "unindexed_period": "full_sync",
    "uncounted_fees": "full_sync",
    "classification_error": "classify_transactions",
    "duplicates": "full_sync",
}


@router.post("/resync/{issue_id}")
async def resync_verification_issue(
    issue_id: int,
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Queue a re-sync job for the wallet associated with a verification issue.

    Maps diagnosis_category to the appropriate job type:
      - missing_staking_rewards -> staking_sync
      - unindexed_period        -> full_sync
      - uncounted_fees          -> full_sync
      - classification_error    -> classify_transactions
      - duplicates              -> full_sync
    """
    user_id = user["user_id"]

    def _resync(conn):
        cur = conn.cursor()
        try:
            # Get wallet_id and diagnosis_category, verify ownership
            cur.execute(
                """
                SELECT vr.wallet_id, vr.diagnosis_category
                FROM verification_results vr
                JOIN wallets w ON w.id = vr.wallet_id
                WHERE vr.id = %s AND w.user_id = %s
                """,
                (issue_id, user_id),
            )
            row = cur.fetchone()
            if row is None:
                return None, None

            wallet_id, diagnosis_category = row

            # Determine job type
            job_type = _RESYNC_JOB_MAP.get(diagnosis_category, "full_sync")

            # Queue the re-sync job
            cur.execute(
                """
                INSERT INTO indexing_jobs (wallet_id, user_id, job_type, status, priority)
                VALUES (%s, %s, %s, 'queued', 8)
                RETURNING id
                """,
                (wallet_id, user_id, job_type),
            )
            job_row = cur.fetchone()
            job_id = job_row[0]

            conn.commit()
            return job_id, job_type
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        job_id, job_type = await run_in_threadpool(_resync, conn)
    finally:
        pool.putconn(conn)

    if job_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verification issue not found",
        )

    return {"message": "Re-sync queued", "job_id": job_id, "job_type": job_type}


# ---------------------------------------------------------------------------
# GET /api/verification/needs-review-count
# ---------------------------------------------------------------------------


@router.get("/needs-review-count", response_model=NeedsReviewCountResponse)
async def get_needs_review_count(
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return total count of unresolved needs_review items across all relevant tables."""
    user_id = user["user_id"]

    def _count(conn):
        cur = conn.cursor()
        try:
            # verification_results
            cur.execute(
                """
                SELECT COUNT(*) FROM verification_results vr
                JOIN wallets w ON w.id = vr.wallet_id
                WHERE w.user_id = %s AND vr.needs_review = TRUE
                """,
                (user_id,),
            )
            vr_count = (cur.fetchone() or (0,))[0]

            # transaction_classifications
            cur.execute(
                """
                SELECT COUNT(*) FROM transaction_classifications tc
                JOIN wallets w ON w.id = tc.wallet_id
                WHERE w.user_id = %s AND tc.needs_review = TRUE
                """,
                (user_id,),
            )
            tc_count = (cur.fetchone() or (0,))[0]

            # capital_gains_ledger
            cur.execute(
                """
                SELECT COUNT(*) FROM capital_gains_ledger
                WHERE user_id = %s AND needs_review = TRUE
                """,
                (user_id,),
            )
            cg_count = (cur.fetchone() or (0,))[0]

            return int(vr_count), int(tc_count), int(cg_count)
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        vr_count, tc_count, cg_count = await run_in_threadpool(_count, conn)
    finally:
        pool.putconn(conn)

    return NeedsReviewCountResponse(
        total=vr_count + tc_count + cg_count,
        verification_results=vr_count,
        transaction_classifications=tc_count,
        capital_gains_ledger=cg_count,
    )
