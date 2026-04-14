"""Transaction ledger API — filtering, pagination, search, classification editing.

Endpoints:
  GET    /api/transactions                        — paginated ledger (UNION ALL on-chain + exchange)
  GET    /api/transactions/review                 — needs_review=true queue sorted by confidence
  PATCH  /api/transactions/{tx_hash}/classification — edit tax_category, notes, mark reviewed
  POST   /api/transactions/apply-changes          — stage ACB recalculation for affected tokens

All endpoints use get_effective_user_with_dek so DEK is available for encrypted column decryption.
All DB calls use run_in_threadpool() to avoid blocking the async event loop.

D-07 in-memory filter strategy:
  SQL only filters on cleartext columns (user_id, wallet_id, block_timestamp, chain, needs_review).
  Encrypted columns (tx_hash, counterparty, direction, action_type, token_id, amount, category)
  are decrypted in Python after fetch, then filtered in-memory before pagination is applied.
"""

import json
import math
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool

import db.crypto as _crypto
from api.dependencies import get_effective_user_with_dek, get_pool_dep
from api.rate_limit import limiter
from db.audit import write_audit
from api.schemas.transactions import (
    ApplyChangesRequest,
    ApplyChangesResponse,
    ClassificationUpdate,
    ReviewQueueResponse,
    TransactionListResponse,
    TransactionResponse,
)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

# Whitelist prevents SQL injection via user-supplied field names in dynamic UPDATE statements.
ALLOWED_UPDATE_FIELDS = {"category", "notes", "needs_review"}

# Divisors for raw on-chain amount -> human-readable
_NEAR_DIVISOR = Decimal("1" + "0" * 24)
_EVM_DIVISOR = Decimal("1" + "0" * 18)


# ---------------------------------------------------------------------------
# Helpers — decryption and row parsing
# ---------------------------------------------------------------------------


def _dec(raw) -> Optional[str]:
    """Decrypt a raw BYTEA value from psycopg2 using the current context DEK.

    Returns None if raw is None.  The EncryptedBytes TypeDecorator is used at the
    SQLAlchemy ORM layer; here we call process_result_value() directly against the
    raw memoryview/bytes returned by psycopg2.

    If raw is already a str (e.g. in tests where mocks return plaintext),
    return it unchanged — EncryptedBytes.process_result_value() operates on bytes only.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    v = _crypto.EncryptedBytes().process_result_value(bytes(raw), None)
    if v is None:
        return None
    return str(v)


def _amount_str(raw_amount, chain: str) -> Optional[str]:
    """Decrypt and convert raw amount to human units based on chain."""
    raw = _dec(raw_amount)
    if raw is None:
        return None
    try:
        divisor = _NEAR_DIVISOR if (chain or "near").lower() == "near" else _EVM_DIVISOR
        return str(Decimal(raw) / divisor)
    except Exception:
        return raw


def _make_onchain_tx(
    t_id: int, chain: str, block_ts,
    tx_hash_raw, direction_raw, counterparty_raw, amount_raw, token_id_raw, action_type_raw,
    tc_category_raw, tc_confidence, tc_needs_review, tc_notes_raw,
    source: str = "on_chain",
) -> dict:
    """Build a transaction dict from raw psycopg2 row with in-Python decryption."""
    tx_hash = _dec(tx_hash_raw) or ""
    direction = _dec(direction_raw) or ""
    counterparty = _dec(counterparty_raw) or ""
    amount = _amount_str(amount_raw, chain)
    token_symbol = _dec(token_id_raw)
    action_type = _dec(action_type_raw)
    category = _dec(tc_category_raw)
    reviewer_notes = _dec(tc_notes_raw)

    # Compute sender/receiver from direction
    if direction == "out":
        sender = ""
        receiver = counterparty
    else:
        sender = counterparty
        receiver = ""

    # Timestamp from nanoseconds → ISO string
    if block_ts is not None:
        import datetime
        try:
            ts_sec = block_ts / 1_000_000_000.0
            dt = datetime.datetime.utcfromtimestamp(ts_sec)
            timestamp_iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            timestamp_iso = None
    else:
        timestamp_iso = None

    return {
        "id": t_id,
        "tx_hash": tx_hash,
        "chain": chain or "",
        "timestamp": timestamp_iso,
        "sender": sender or None,
        "receiver": receiver or None,
        "amount": amount,
        "token_symbol": token_symbol,
        "action_type": action_type,
        "tax_category": category,
        "sub_category": None,
        "confidence_score": float(tc_confidence) if tc_confidence is not None else None,
        "needs_review": bool(tc_needs_review) if tc_needs_review is not None else False,
        "reviewer_notes": reviewer_notes,
        "source": source,
        # raw values for in-memory filtering (not exposed in response)
        "_direction": direction,
        "_token_symbol": token_symbol,
    }


def _dict_to_tx_response(d: dict) -> TransactionResponse:
    """Convert our internal dict to a TransactionResponse."""
    return TransactionResponse(
        tx_hash=d["tx_hash"],
        chain=d["chain"],
        timestamp=d["timestamp"],
        sender=d["sender"],
        receiver=d["receiver"],
        amount=d["amount"],
        token_symbol=d["token_symbol"],
        action_type=d["action_type"],
        tax_category=d["tax_category"],
        sub_category=d["sub_category"],
        confidence_score=d["confidence_score"],
        needs_review=d["needs_review"],
        reviewer_notes=d["reviewer_notes"],
        source=d["source"],
    )


# ---------------------------------------------------------------------------
# GET /api/transactions — Transaction ledger with filtering and pagination
# ---------------------------------------------------------------------------


@router.get("/review", response_model=ReviewQueueResponse)
async def get_review_queue(
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """Return all transactions flagged for review (needs_review=true).

    Items are sorted by confidence_score ASC (least confident first).
    Includes counts grouped by tax_category for dashboard display.

    NOTE: This route must be registered BEFORE /{tx_hash}/classification to
    prevent FastAPI from interpreting "review" as a tx_hash path parameter.

    D-07: SQL filters only on cleartext columns (user_id, wallet_id, needs_review=Boolean).
    All encrypted columns (tx_hash, counterparty, direction, category, notes, amount) are
    decrypted in Python after fetch.
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

            onchain_rows = []
            if wallet_ids:
                placeholders = ",".join(["%s"] * len(wallet_ids))
                # D-07: Only cleartext columns in WHERE. needs_review is Boolean (cleartext).
                # Encrypted columns (tx_hash, direction, counterparty, amount, token_id,
                # action_type, category, notes) fetched as raw BYTEA, decrypted in Python.
                cur.execute(
                    f"""
                    SELECT
                        t.id, t.chain, t.block_timestamp,
                        t.tx_hash, t.direction, t.counterparty, t.amount, t.token_id, t.action_type,
                        tc.category, tc.confidence, tc.needs_review, tc.notes
                    FROM transactions t
                    LEFT JOIN transaction_classifications tc ON tc.transaction_id = t.id
                    WHERE t.wallet_id IN ({placeholders})
                      AND tc.needs_review = TRUE
                    ORDER BY tc.confidence ASC NULLS LAST, t.block_timestamp ASC
                    """,
                    list(wallet_ids),
                )
                onchain_rows = cur.fetchall()

            # Exchange side — category/notes are encrypted; needs_review is cleartext
            cur.execute(
                """
                SELECT
                    et.id, et.tx_date, et.tx_id, et.exchange, et.quantity, et.asset, et.tx_type,
                    tc.category, tc.confidence, tc.needs_review, tc.notes
                FROM transaction_classifications tc
                JOIN exchange_transactions et ON tc.exchange_transaction_id = et.id
                WHERE tc.user_id = %s
                  AND tc.needs_review = TRUE
                  AND tc.exchange_transaction_id IS NOT NULL
                ORDER BY tc.confidence ASC NULLS LAST, et.tx_date ASC
                """,
                (user_id,),
            )
            exchange_rows = cur.fetchall()
            return onchain_rows, exchange_rows
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        onchain_rows, exchange_rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    # Decrypt and build response items
    items = []

    for row in onchain_rows:
        (t_id, chain, block_ts,
         tx_hash_raw, direction_raw, counterparty_raw, amount_raw, token_id_raw, action_type_raw,
         tc_category_raw, tc_confidence, tc_needs_review, tc_notes_raw) = row
        d = _make_onchain_tx(
            t_id=t_id, chain=chain, block_ts=block_ts,
            tx_hash_raw=tx_hash_raw, direction_raw=direction_raw,
            counterparty_raw=counterparty_raw, amount_raw=amount_raw,
            token_id_raw=token_id_raw, action_type_raw=action_type_raw,
            tc_category_raw=tc_category_raw, tc_confidence=tc_confidence,
            tc_needs_review=tc_needs_review, tc_notes_raw=tc_notes_raw,
            source="on_chain",
        )
        items.append(_dict_to_tx_response(d))

    for row in exchange_rows:
        (et_id, tx_date, tx_id, exchange, quantity, asset, tx_type,
         tc_category_raw, tc_confidence, tc_needs_review, tc_notes_raw) = row
        # Exchange transactions: category/notes are encrypted; tx_id, exchange, asset, tx_type cleartext
        category = _dec(tc_category_raw)
        reviewer_notes = _dec(tc_notes_raw)
        timestamp_iso = tx_date.strftime("%Y-%m-%dT%H:%M:%S") if tx_date else None
        items.append(TransactionResponse(
            tx_hash=str(tx_id) if tx_id else "",
            chain="exchange",
            timestamp=timestamp_iso,
            sender=str(exchange) if exchange else None,
            receiver=None,
            amount=str(quantity) if quantity is not None else None,
            token_symbol=str(asset) if asset else None,
            action_type=str(tx_type) if tx_type else None,
            tax_category=category,
            sub_category=None,
            confidence_score=float(tc_confidence) if tc_confidence is not None else None,
            needs_review=bool(tc_needs_review) if tc_needs_review is not None else False,
            reviewer_notes=reviewer_notes,
            source="exchange",
        ))

    total = len(items)

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
    user: dict = Depends(get_effective_user_with_dek),
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

    D-07 in-memory filter strategy:
      SQL only filters on cleartext columns: user_id, wallet_id, block_timestamp (for dates),
      chain (cleartext String), needs_review (Boolean cleartext).
      Encrypted columns (tx_hash, counterparty, direction, action_type, token_id, amount,
      category, notes) are decrypted in Python then filtered in-memory.
      Pagination is applied AFTER in-memory filtering.
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

            # ----------------------------------------------------------------
            # Build on-chain side (D-07: only cleartext column filters in SQL)
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
            # chain is cleartext — kept in SQL
            if chain and chain.lower() != "exchange":
                onchain_where_clauses.append("t.chain ILIKE %s")
                onchain_extra_params.append(chain)
            # needs_review is Boolean (cleartext) — kept in SQL
            if needs_review is not None:
                onchain_where_clauses.append("COALESCE(tc.needs_review, FALSE) = %s")
                onchain_extra_params.append(needs_review)
            # REMOVED: tax_category (tc.category is EncryptedBytes) — filter in Python
            # REMOVED: asset (t.token_id is EncryptedBytes) — filter in Python
            # REMOVED: search on tx_hash / counterparty (EncryptedBytes) — filter in Python

            onchain_rows = []
            if wallet_ids:
                placeholders = ",".join(["%s"] * len(wallet_ids))
                extra_where = ""
                if onchain_where_clauses:
                    extra_where = "AND " + " AND ".join(onchain_where_clauses)

                # Fetch raw encrypted columns — decrypted in Python below
                onchain_sql = f"""
                    SELECT
                        t.id, t.chain, t.block_timestamp,
                        t.tx_hash, t.direction, t.counterparty, t.amount, t.token_id, t.action_type,
                        tc.category, tc.confidence, tc.needs_review, tc.notes
                    FROM transactions t
                    LEFT JOIN transaction_classifications tc
                        ON tc.transaction_id = t.id
                    WHERE t.wallet_id IN ({placeholders})
                    {extra_where}
                    ORDER BY t.block_timestamp DESC NULLS LAST
                """
                cur.execute(onchain_sql, list(wallet_ids) + onchain_extra_params)
                onchain_rows = cur.fetchall()

            # ----------------------------------------------------------------
            # Build exchange side
            # ----------------------------------------------------------------
            exchange_where_clauses = ["tc.user_id = %s", "tc.exchange_transaction_id IS NOT NULL"]
            exchange_params: list = [user_id]

            if start_date:
                exchange_where_clauses.append("et.tx_date >= %s::DATE")
                exchange_params.append(start_date)
            if end_date:
                exchange_where_clauses.append("et.tx_date <= %s::DATE")
                exchange_params.append(end_date)
            # needs_review is cleartext — kept in SQL
            if needs_review is not None:
                exchange_where_clauses.append("COALESCE(tc.needs_review, FALSE) = %s")
                exchange_params.append(needs_review)
            # REMOVED: tax_category/asset/search on encrypted columns — filter in Python

            exchange_where = " AND ".join(exchange_where_clauses)
            exchange_sql = f"""
                SELECT
                    et.id, et.tx_date, et.tx_id, et.exchange, et.quantity, et.asset, et.tx_type,
                    tc.category, tc.confidence, tc.needs_review, tc.notes
                FROM transaction_classifications tc
                JOIN exchange_transactions et ON tc.exchange_transaction_id = et.id
                WHERE {exchange_where}
                ORDER BY et.tx_date DESC NULLS LAST
            """
            cur.execute(exchange_sql, exchange_params)
            exchange_rows = cur.fetchall()
            return onchain_rows, exchange_rows
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        onchain_rows, exchange_rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    # ----------------------------------------------------------------
    # Decrypt and build candidate list
    # ----------------------------------------------------------------
    candidates = []

    for row in onchain_rows:
        (t_id, t_chain, block_ts,
         tx_hash_raw, direction_raw, counterparty_raw, amount_raw, token_id_raw, action_type_raw,
         tc_category_raw, tc_confidence, tc_needs_review, tc_notes_raw) = row
        d = _make_onchain_tx(
            t_id=t_id, chain=t_chain, block_ts=block_ts,
            tx_hash_raw=tx_hash_raw, direction_raw=direction_raw,
            counterparty_raw=counterparty_raw, amount_raw=amount_raw,
            token_id_raw=token_id_raw, action_type_raw=action_type_raw,
            tc_category_raw=tc_category_raw, tc_confidence=tc_confidence,
            tc_needs_review=tc_needs_review, tc_notes_raw=tc_notes_raw,
            source="on_chain",
        )
        d["_sort_ts"] = block_ts or 0
        candidates.append(d)

    for row in exchange_rows:
        (et_id, tx_date, tx_id, exchange, quantity, asset, tx_type,
         tc_category_raw, tc_confidence, tc_needs_review, tc_notes_raw) = row
        category = _dec(tc_category_raw)
        reviewer_notes = _dec(tc_notes_raw)
        timestamp_iso = tx_date.strftime("%Y-%m-%dT%H:%M:%S") if tx_date else None
        sort_ts = int(tx_date.timestamp() * 1_000_000_000) if tx_date else 0
        candidates.append({
            "id": et_id,
            "tx_hash": str(tx_id) if tx_id else "",
            "chain": "exchange",
            "timestamp": timestamp_iso,
            "sender": str(exchange) if exchange else None,
            "receiver": None,
            "amount": str(quantity) if quantity is not None else None,
            "token_symbol": str(asset) if asset else None,
            "action_type": str(tx_type) if tx_type else None,
            "tax_category": category,
            "sub_category": None,
            "confidence_score": float(tc_confidence) if tc_confidence is not None else None,
            "needs_review": bool(tc_needs_review) if tc_needs_review is not None else False,
            "reviewer_notes": reviewer_notes,
            "source": "exchange",
            "_direction": "",
            "_token_symbol": str(asset) if asset else None,
            "_sort_ts": sort_ts,
        })

    # ----------------------------------------------------------------
    # In-memory filters for encrypted-column predicates (D-07)
    # ----------------------------------------------------------------
    if chain and chain.lower() == "exchange":
        candidates = [c for c in candidates if c["chain"] == "exchange"]
    elif chain:
        candidates = [c for c in candidates if c["chain"] != "exchange"]

    if tax_category:
        candidates = [c for c in candidates if (c.get("tax_category") or "").lower() == tax_category.lower()]

    if asset:
        candidates = [
            c for c in candidates
            if (c.get("_token_symbol") or "").lower() == asset.lower()
            or asset.lower() in (c.get("_token_symbol") or "").lower()
        ]

    if search:
        s = search.lower()
        candidates = [
            c for c in candidates
            if s in (c.get("tx_hash") or "").lower()
            or s in (c.get("sender") or "").lower()
            or s in (c.get("receiver") or "").lower()
        ]

    # Sort by timestamp DESC.  _sort_ts is an integer nanosecond epoch for on-chain rows
    # and exchange rows (computed from tx_date).  Sort reversed so highest value is first.
    # Use "" as a fallback for None so str/int comparisons don't raise TypeError.
    candidates.sort(key=lambda c: c.get("_sort_ts") or 0, reverse=True)

    # Apply pagination AFTER in-memory filtering
    total = len(candidates)
    offset = (page - 1) * per_page
    page_candidates = candidates[offset: offset + per_page]

    transactions = []
    for c in page_candidates:
        transactions.append(TransactionResponse(
            tx_hash=c["tx_hash"],
            chain=c["chain"],
            timestamp=c["timestamp"],
            sender=c["sender"],
            receiver=c["receiver"],
            amount=c["amount"],
            token_symbol=c["token_symbol"],
            action_type=c["action_type"],
            tax_category=c["tax_category"],
            sub_category=c["sub_category"],
            confidence_score=c["confidence_score"],
            needs_review=c["needs_review"],
            reviewer_notes=c["reviewer_notes"],
            source=c["source"],
        ))

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
    user: dict = Depends(get_effective_user_with_dek),
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
    # Capture the DEK in the async context before entering the thread pool.
    # anyio threads do NOT automatically copy ContextVar values from the calling
    # coroutine, so write_audit() (which calls get_dek()) would raise without this.
    _dek_for_thread = _crypto.get_dek()

    def _update(conn):
        # Re-inject DEK into this thread's ContextVar context so write_audit() works.
        _crypto.set_dek(_dek_for_thread)
        cur = conn.cursor()
        try:
            # Verify ownership and fetch old classification values for audit
            cur.execute(
                """
                SELECT tc.id, tc.category, tc.confidence
                FROM transaction_classifications tc
                LEFT JOIN transactions t ON tc.transaction_id = t.id
                LEFT JOIN wallets w ON t.wallet_id = w.id
                LEFT JOIN exchange_transactions et ON tc.exchange_transaction_id = et.id
                WHERE tc.id = %s
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
                set_clauses.append("category = %s")
                params.append(body.tax_category)
            if body.reviewer_notes is not None:
                set_clauses.append("notes = %s")
                params.append(body.reviewer_notes)
            if body.needs_review is not None:
                set_clauses.append("needs_review = %s")
                params.append(body.needs_review)
                if body.needs_review is False:
                    set_clauses.append("confirmed_at = NOW()")

            set_sql = ", ".join(set_clauses)
            params.append(classification_id)

            cur.execute(
                f"""
                UPDATE transaction_classifications
                SET {set_sql}
                WHERE id = %s
                """,
                params,
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
    user: dict = Depends(get_effective_user_with_dek),
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
                    LEFT JOIN transactions t ON tc.transaction_id = t.id
                    LEFT JOIN exchange_transactions et ON tc.exchange_transaction_id = et.id
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
