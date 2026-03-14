"""Transaction ledger API — filtering, pagination, search, classification editing.

Endpoints:
  GET    /api/transactions                        — paginated ledger (UNION ALL on-chain + exchange)
  GET    /api/transactions/review                 — needs_review=true queue sorted by confidence
  PATCH  /api/transactions/{tx_hash}/classification — edit tax_category, notes, mark reviewed
  POST   /api/transactions/apply-changes          — stage ACB recalculation for affected tokens

All endpoints use get_effective_user so accountants transparently query client data.
All DB calls use run_in_threadpool() to avoid blocking the async event loop.

UNION ALL query pattern:
  - On-chain: transactions table JOIN wallets (filter by wallet.user_id)
  - Exchange: exchange_transactions JOIN transaction_classifications (filter by user_id)
  - LEFT JOIN transaction_classifications for tax classification data on on-chain side
  - Window function COUNT(*) OVER() for total count in a single query pass
"""

import json
import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool

from api.dependencies import get_effective_user, get_pool_dep
from api.rate_limit import limiter
from db.audit import write_audit
from api.schemas.transactions import (
    ApplyChangesRequest,
    ApplyChangesResponse,
    ClassificationUpdate,
    ReviewQueueResponse,
    TransactionFilters,
    TransactionListResponse,
    TransactionResponse,
)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

# Whitelist prevents SQL injection via user-supplied field names in dynamic UPDATE statements.
ALLOWED_UPDATE_FIELDS = {"tax_category", "sub_category", "reviewer_notes", "needs_review"}


# ---------------------------------------------------------------------------
# Helpers — row parsing
# ---------------------------------------------------------------------------


def _row_to_tx(row) -> TransactionResponse:
    """Convert a UNION ALL query row into a TransactionResponse.

    Row columns (0-indexed):
      0  tx_hash
      1  chain
      2  timestamp_iso
      3  sender
      4  receiver
      5  amount_str
      6  token_symbol
      7  action_type
      8  tax_category
      9  sub_category
      10 confidence_score
      11 needs_review
      12 reviewer_notes
      13 source
      14 total_count  (COUNT(*) OVER() — not included in response)
    """
    (
        tx_hash, chain, timestamp_iso, sender, receiver, amount_str,
        token_symbol, action_type, tax_category, sub_category,
        confidence_score, needs_review, reviewer_notes, source, _total,
    ) = row
    return TransactionResponse(
        tx_hash=str(tx_hash) if tx_hash is not None else "",
        chain=str(chain) if chain is not None else "",
        timestamp=timestamp_iso if timestamp_iso is not None else None,
        sender=sender if sender is not None else None,
        receiver=receiver if receiver is not None else None,
        amount=str(amount_str) if amount_str is not None else None,
        token_symbol=token_symbol if token_symbol is not None else None,
        action_type=action_type if action_type is not None else None,
        tax_category=tax_category if tax_category is not None else None,
        sub_category=sub_category if sub_category is not None else None,
        confidence_score=float(confidence_score) if confidence_score is not None else None,
        needs_review=bool(needs_review) if needs_review is not None else False,
        reviewer_notes=reviewer_notes if reviewer_notes is not None else None,
        source=str(source) if source is not None else "on_chain",
    )


# ---------------------------------------------------------------------------
# GET /api/transactions — Transaction ledger with filtering and pagination
# ---------------------------------------------------------------------------


@router.get("/review", response_model=ReviewQueueResponse)
async def get_review_queue(
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return all transactions flagged for review (needs_review=true).

    Items are sorted by confidence_score ASC (least confident first).
    Includes counts grouped by tax_category for dashboard display.

    NOTE: This route must be registered BEFORE /{tx_hash}/classification to
    prevent FastAPI from interpreting "review" as a tx_hash path parameter.
    """
    user_id = user["user_id"]

    def _query(conn):
        cur = conn.cursor()
        try:
            # Fetch wallet_ids for the user
            cur.execute(
                "SELECT id FROM wallets WHERE user_id = %s",
                (user_id,),
            )
            wallet_rows = cur.fetchall()
            wallet_ids = [r[0] for r in wallet_rows]

            # Build on-chain side (only if user has wallets)
            onchain_sql = ""
            onchain_params: list = []
            if wallet_ids:
                placeholders = ",".join(["%s"] * len(wallet_ids))
                onchain_sql = f"""
                    SELECT
                        COALESCE(t.tx_hash, '') AS tx_hash,
                        t.chain,
                        TO_CHAR(
                            TO_TIMESTAMP(t.block_timestamp / 1000000000.0),
                            'YYYY-MM-DD"T"HH24:MI:SS'
                        ) AS timestamp_iso,
                        COALESCE(t.sender_id, '') AS sender,
                        COALESCE(t.receiver_id, '') AS receiver,
                        CAST(t.amount AS TEXT) AS amount_str,
                        COALESCE(t.token_id, '') AS token_symbol,
                        COALESCE(t.action_type, '') AS action_type,
                        COALESCE(tc.tax_category, '') AS tax_category,
                        tc.sub_category,
                        tc.confidence_score,
                        COALESCE(tc.needs_review, FALSE) AS needs_review,
                        tc.reviewer_notes,
                        'on_chain' AS source,
                        t.block_timestamp AS sort_ts
                    FROM transactions t
                    LEFT JOIN transaction_classifications tc
                        ON tc.tx_hash = t.tx_hash AND tc.chain = t.chain
                    WHERE t.wallet_id IN ({placeholders})
                      AND tc.needs_review = TRUE
                """
                onchain_params = list(wallet_ids)

            # Exchange side
            exchange_sql = """
                SELECT
                    COALESCE(et.tx_id, '') AS tx_hash,
                    'exchange' AS chain,
                    TO_CHAR(et.tx_date, 'YYYY-MM-DD"T"HH24:MI:SS') AS timestamp_iso,
                    et.exchange AS sender,
                    NULL AS receiver,
                    CAST(et.quantity AS TEXT) AS amount_str,
                    COALESCE(et.asset, '') AS token_symbol,
                    COALESCE(et.tx_type, '') AS action_type,
                    COALESCE(tc.tax_category, '') AS tax_category,
                    tc.sub_category,
                    tc.confidence_score,
                    COALESCE(tc.needs_review, FALSE) AS needs_review,
                    tc.reviewer_notes,
                    'exchange' AS source,
                    EXTRACT(EPOCH FROM et.tx_date)::BIGINT * 1000000000 AS sort_ts
                FROM transaction_classifications tc
                JOIN exchange_transactions et ON tc.tx_hash = et.tx_id
                WHERE tc.user_id = %s
                  AND tc.needs_review = TRUE
                  AND tc.chain = 'exchange'
            """
            exchange_params = [user_id]

            # Build UNION ALL (or just exchange if no wallets)
            if onchain_sql:
                full_sql = f"""
                    SELECT
                        tx_hash, chain, timestamp_iso, sender, receiver,
                        amount_str, token_symbol, action_type, tax_category,
                        sub_category, confidence_score, needs_review,
                        reviewer_notes, source,
                        COUNT(*) OVER() AS total_count
                    FROM (
                        {onchain_sql}
                        UNION ALL
                        {exchange_sql}
                    ) combined
                    ORDER BY confidence_score ASC NULLS LAST, sort_ts ASC
                """
                all_params = onchain_params + exchange_params
            else:
                full_sql = f"""
                    SELECT
                        tx_hash, chain, timestamp_iso, sender, receiver,
                        amount_str, token_symbol, action_type, tax_category,
                        sub_category, confidence_score, needs_review,
                        reviewer_notes, source,
                        COUNT(*) OVER() AS total_count
                    FROM (
                        {exchange_sql}
                    ) combined
                    ORDER BY confidence_score ASC NULLS LAST, sort_ts ASC
                """
                all_params = exchange_params

            cur.execute(full_sql, all_params)
            rows = cur.fetchall()
            return rows
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    items = [_row_to_tx(r) for r in rows]
    total = rows[0][14] if rows else 0

    # Build counts_by_category
    counts_by_category: dict = {}
    for item in items:
        cat = item.tax_category or ""
        counts_by_category[cat] = counts_by_category.get(cat, 0) + 1

    return ReviewQueueResponse(
        items=items,
        counts_by_category=counts_by_category,
        total=total,
    )


@router.get("", response_model=TransactionListResponse)
@limiter.limit("60/minute")
async def list_transactions(
    request: Request,
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    tax_category: Optional[str] = Query(default=None),
    asset: Optional[str] = Query(default=None),
    chain: Optional[str] = Query(default=None),
    needs_review: Optional[bool] = Query(default=None),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
):
    """Return paginated transaction ledger for the authenticated user.

    Queries:
      - NEAR/EVM transactions joined with transaction_classifications
      - exchange_transactions joined with transaction_classifications
      Both sides via UNION ALL, ordered by timestamp DESC.

    Filters applied as WHERE clauses on the combined result.
    Total count returned via COUNT(*) OVER() window function.
    """
    user_id = user["user_id"]
    offset = (page - 1) * per_page

    def _query(conn):
        cur = conn.cursor()
        try:
            # Fetch wallet_ids for the user
            cur.execute(
                "SELECT id FROM wallets WHERE user_id = %s",
                (user_id,),
            )
            wallet_rows = cur.fetchall()
            wallet_ids = [r[0] for r in wallet_rows]

            # ----------------------------------------------------------------
            # Build on-chain side
            # ----------------------------------------------------------------
            onchain_where_clauses = []
            onchain_extra_params: list = []

            if start_date:
                onchain_where_clauses.append(
                    "TO_TIMESTAMP(t.block_timestamp / 1000000000.0) >= %s::TIMESTAMPTZ"
                )
                onchain_extra_params.append(start_date)
            if end_date:
                onchain_where_clauses.append(
                    "TO_TIMESTAMP(t.block_timestamp / 1000000000.0) <= %s::TIMESTAMPTZ"
                )
                onchain_extra_params.append(end_date)
            if tax_category:
                onchain_where_clauses.append("tc.tax_category = %s")
                onchain_extra_params.append(tax_category)
            if asset:
                onchain_where_clauses.append("t.token_id ILIKE %s")
                onchain_extra_params.append(f"%{asset}%")
            if chain:
                onchain_where_clauses.append("t.chain ILIKE %s")
                onchain_extra_params.append(chain)
            if needs_review is not None:
                onchain_where_clauses.append("COALESCE(tc.needs_review, FALSE) = %s")
                onchain_extra_params.append(needs_review)
            if search:
                onchain_where_clauses.append(
                    "(t.tx_hash ILIKE %s OR t.sender_id ILIKE %s OR t.receiver_id ILIKE %s)"
                )
                search_pat = f"%{search}%"
                onchain_extra_params.extend([search_pat, search_pat, search_pat])

            onchain_sql = ""
            onchain_params: list = []
            if wallet_ids:
                placeholders = ",".join(["%s"] * len(wallet_ids))
                extra_where = ""
                if onchain_where_clauses:
                    extra_where = "AND " + " AND ".join(onchain_where_clauses)

                onchain_sql = f"""
                    SELECT
                        COALESCE(t.tx_hash, '') AS tx_hash,
                        t.chain,
                        TO_CHAR(
                            TO_TIMESTAMP(t.block_timestamp / 1000000000.0),
                            'YYYY-MM-DD"T"HH24:MI:SS'
                        ) AS timestamp_iso,
                        COALESCE(t.sender_id, '') AS sender,
                        COALESCE(t.receiver_id, '') AS receiver,
                        CAST(t.amount AS TEXT) AS amount_str,
                        COALESCE(t.token_id, '') AS token_symbol,
                        COALESCE(t.action_type, '') AS action_type,
                        COALESCE(tc.tax_category, '') AS tax_category,
                        tc.sub_category,
                        tc.confidence_score,
                        COALESCE(tc.needs_review, FALSE) AS needs_review,
                        tc.reviewer_notes,
                        'on_chain' AS source,
                        t.block_timestamp AS sort_ts
                    FROM transactions t
                    LEFT JOIN transaction_classifications tc
                        ON tc.tx_hash = t.tx_hash AND tc.chain = t.chain
                    WHERE t.wallet_id IN ({placeholders})
                    {extra_where}
                """
                onchain_params = list(wallet_ids) + onchain_extra_params

            # ----------------------------------------------------------------
            # Build exchange side
            # ----------------------------------------------------------------
            exchange_where_clauses = ["tc.user_id = %s", "tc.chain = 'exchange'"]
            exchange_params: list = [user_id]

            if start_date:
                exchange_where_clauses.append("et.tx_date >= %s::DATE")
                exchange_params.append(start_date)
            if end_date:
                exchange_where_clauses.append("et.tx_date <= %s::DATE")
                exchange_params.append(end_date)
            if tax_category:
                exchange_where_clauses.append("tc.tax_category = %s")
                exchange_params.append(tax_category)
            if asset:
                exchange_where_clauses.append("et.asset ILIKE %s")
                exchange_params.append(f"%{asset}%")
            if chain:
                # Exchange transactions are only returned when chain filter is 'exchange'
                exchange_where_clauses.append("'exchange' ILIKE %s")
                exchange_params.append(f"%{chain}%")
            if needs_review is not None:
                exchange_where_clauses.append("COALESCE(tc.needs_review, FALSE) = %s")
                exchange_params.append(needs_review)
            if search:
                exchange_where_clauses.append(
                    "(et.tx_id ILIKE %s OR et.exchange ILIKE %s)"
                )
                search_pat = f"%{search}%"
                exchange_params.extend([search_pat, search_pat])

            exchange_where = " AND ".join(exchange_where_clauses)
            exchange_sql = f"""
                SELECT
                    COALESCE(et.tx_id, '') AS tx_hash,
                    'exchange' AS chain,
                    TO_CHAR(et.tx_date, 'YYYY-MM-DD"T"HH24:MI:SS') AS timestamp_iso,
                    et.exchange AS sender,
                    NULL AS receiver,
                    CAST(et.quantity AS TEXT) AS amount_str,
                    COALESCE(et.asset, '') AS token_symbol,
                    COALESCE(et.tx_type, '') AS action_type,
                    COALESCE(tc.tax_category, '') AS tax_category,
                    tc.sub_category,
                    tc.confidence_score,
                    COALESCE(tc.needs_review, FALSE) AS needs_review,
                    tc.reviewer_notes,
                    'exchange' AS source,
                    EXTRACT(EPOCH FROM et.tx_date)::BIGINT * 1000000000 AS sort_ts
                FROM transaction_classifications tc
                JOIN exchange_transactions et ON tc.tx_hash = et.tx_id
                WHERE {exchange_where}
            """

            # ----------------------------------------------------------------
            # Combine: UNION ALL + window count + pagination
            # ----------------------------------------------------------------
            if onchain_sql:
                inner_sql = f"({onchain_sql} UNION ALL {exchange_sql}) combined"
                all_params = onchain_params + exchange_params
            else:
                inner_sql = f"({exchange_sql}) combined"
                all_params = exchange_params

            full_sql = f"""
                SELECT
                    tx_hash, chain, timestamp_iso, sender, receiver,
                    amount_str, token_symbol, action_type, tax_category,
                    sub_category, confidence_score, needs_review,
                    reviewer_notes, source,
                    COUNT(*) OVER() AS total_count
                FROM {inner_sql}
                ORDER BY sort_ts DESC NULLS LAST
                LIMIT %s OFFSET %s
            """
            all_params = all_params + [per_page, offset]

            cur.execute(full_sql, all_params)
            rows = cur.fetchall()
            return rows
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    total = rows[0][14] if rows else 0
    transactions = [_row_to_tx(r) for r in rows]
    pages = math.ceil(total / per_page) if total > 0 else 0

    return TransactionListResponse(
        transactions=transactions,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


# ---------------------------------------------------------------------------
# PATCH /api/transactions/{tx_hash}/classification — Edit classification
# ---------------------------------------------------------------------------


@router.patch("/{tx_hash}/classification")
async def patch_classification(
    tx_hash: str,
    body: ClassificationUpdate,
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Update the classification for a transaction.

    Verifies the transaction belongs to the authenticated user (via wallet_id
    or user_id for exchange transactions). Updates transaction_classifications:
      - tax_category (if provided)
      - sub_category (if provided)
      - reviewer_notes (if provided)
      - needs_review (if provided) — also sets reviewed_at=NOW() when False
      - updated_at = NOW() always

    Returns 404 if the transaction is not found for the user.
    """
    user_id = user["user_id"]

    def _update(conn):
        cur = conn.cursor()
        try:
            # Verify ownership and fetch old classification values for audit
            cur.execute(
                """
                SELECT tc.id, tc.tax_category, tc.confidence_score
                FROM transaction_classifications tc
                LEFT JOIN transactions t ON tc.tx_hash = t.tx_hash
                LEFT JOIN wallets w ON t.wallet_id = w.id
                LEFT JOIN exchange_transactions et ON tc.tx_hash = et.tx_id
                WHERE tc.tx_hash = %s
                  AND (
                    (w.user_id = %s)
                    OR (tc.user_id = %s AND et.id IS NOT NULL)
                  )
                LIMIT 1
                """,
                (tx_hash, user_id, user_id),
            )
            row = cur.fetchone()
            if row is None:
                return None

            classification_id, old_category, old_confidence = row

            # Build dynamic UPDATE statement
            set_clauses = ["updated_at = NOW()"]
            params: list = []

            if body.tax_category is not None:
                set_clauses.append("tax_category = %s")
                params.append(body.tax_category)
            if body.sub_category is not None:
                set_clauses.append("sub_category = %s")
                params.append(body.sub_category)
            if body.reviewer_notes is not None:
                set_clauses.append("reviewer_notes = %s")
                params.append(body.reviewer_notes)
            if body.needs_review is not None:
                set_clauses.append("needs_review = %s")
                params.append(body.needs_review)
                if body.needs_review is False:
                    set_clauses.append("reviewed_at = NOW()")

            set_sql = ", ".join(set_clauses)
            params.append(tx_hash)
            params.append(user_id)

            cur.execute(
                f"""
                UPDATE transaction_classifications
                SET {set_sql}
                WHERE tx_hash = %s
                  AND (
                    user_id = %s
                    OR id IN (
                        SELECT tc2.id
                        FROM transaction_classifications tc2
                        JOIN transactions t2 ON tc2.tx_hash = t2.tx_hash
                        JOIN wallets w2 ON t2.wallet_id = w2.id
                        WHERE w2.user_id = %s AND tc2.tx_hash = %s
                    )
                  )
                """,
                params + [user_id, tx_hash],
            )

            # Write audit row for the manual classification edit
            new_category = body.tax_category if body.tax_category is not None else old_category
            write_audit(
                conn,
                user_id=user_id,
                entity_type="transaction_classification",
                entity_id=classification_id,
                action="reclassify",
                old_value={
                    "category": old_category,
                    "confidence": float(old_confidence) if old_confidence is not None else None,
                },
                new_value={
                    "category": new_category,
                    "reviewer_notes": body.reviewer_notes,
                    "needs_review": body.needs_review,
                },
                actor_type="user",
            )

            conn.commit()
            return {"tx_hash": tx_hash, "updated": True}
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        result = await run_in_threadpool(_update, conn)
    finally:
        pool.putconn(conn)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found or access denied",
        )

    return result


# ---------------------------------------------------------------------------
# POST /api/transactions/apply-changes — Trigger ACB recalculation
# ---------------------------------------------------------------------------


@router.post("/apply-changes", response_model=ApplyChangesResponse)
async def apply_changes(
    body: ApplyChangesRequest,
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Stage ACB recalculation for affected tokens.

    Accepts an optional list of token_symbols to recalculate. If not provided,
    finds all tokens with recent classification edits (updated_at > last
    calculate_acb job completion).

    Inserts a calculate_acb job into indexing_jobs with a JSON cursor
    containing the affected token symbols. Returns job_id for polling.
    """
    user_id = user["user_id"]
    token_symbols = body.token_symbols

    def _enqueue(conn):
        cur = conn.cursor()
        try:
            effective_tokens = token_symbols

            # If no tokens specified, find tokens with recent edits
            if not effective_tokens:
                cur.execute(
                    """
                    SELECT DISTINCT
                        COALESCE(t.token_id, et.asset) AS token_sym
                    FROM transaction_classifications tc
                    LEFT JOIN transactions t ON tc.tx_hash = t.tx_hash
                    LEFT JOIN exchange_transactions et ON tc.tx_hash = et.tx_id
                    LEFT JOIN wallets w ON t.wallet_id = w.id
                    WHERE (w.user_id = %s OR tc.user_id = %s)
                      AND tc.updated_at > COALESCE(
                          (
                              SELECT completed_at
                              FROM indexing_jobs
                              WHERE user_id = %s
                                AND job_type = 'calculate_acb'
                                AND status = 'completed'
                              ORDER BY completed_at DESC
                              LIMIT 1
                          ),
                          '1970-01-01'::TIMESTAMPTZ
                      )
                    """,
                    (user_id, user_id, user_id),
                )
                token_rows = cur.fetchall()
                effective_tokens = [r[0] for r in token_rows if r[0]]

            # Get the primary wallet for this user (for job association)
            cur.execute(
                "SELECT id FROM wallets WHERE user_id = %s ORDER BY id LIMIT 1",
                (user_id,),
            )
            wallet_row = cur.fetchone()
            wallet_id = wallet_row[0] if wallet_row else None

            # Build cursor JSON with token_symbols for targeted recalc
            cursor_data = json.dumps({"token_symbols": effective_tokens or []})

            cur.execute(
                """
                INSERT INTO indexing_jobs (wallet_id, user_id, job_type, status, priority, cursor)
                VALUES (%s, %s, 'calculate_acb', 'queued', 5, %s)
                RETURNING id
                """,
                (wallet_id, user_id, cursor_data),
            )
            row = cur.fetchone()
            conn.commit()
            job_id = row[0] if row else None
            return job_id, effective_tokens
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        job_id, effective_tokens = await run_in_threadpool(_enqueue, conn)
    finally:
        pool.putconn(conn)

    if job_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue ACB recalculation job",
        )

    return ApplyChangesResponse(
        job_id=job_id,
        message="ACB recalculation queued",
        token_symbols=effective_tokens or None,
    )
