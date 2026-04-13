"""Dedup HMAC helpers for encrypted write paths (D-28).

Provides insert_transaction_with_dedup() and insert_acb_snapshot_with_dedup()
which compute the HMAC dedup surrogates and perform ON CONFLICT DO UPDATE
upserts into the respective tables.

These helpers operate at the psycopg2 connection level (matching the existing
write paths in indexers/) while using EncryptedBytes to encrypt all in-scope
columns before binding parameters.

Caller contract:
  - A valid DEK must be set in the current context via db.crypto.set_dek()
    before calling either function. If no DEK is set, get_dek() inside
    EncryptedBytes.process_bind_param() will raise RuntimeError (fail-closed).
  - The psycopg2 connection must be within the caller's transaction boundary
    (callers are responsible for commit/rollback).

Example (near_fetcher):
    from db.dedup_hmac_helpers import insert_transaction_with_dedup

    conn = self.db_pool.getconn()
    try:
        for row in rows:
            insert_transaction_with_dedup(conn, **row)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        self.db_pool.putconn(conn)
"""

import logging
from typing import Any

from db.crypto import (
    EncryptedBytes,
    compute_tx_dedup_hmac,
    compute_acb_dedup_hmac,
    get_dek,  # noqa: F401 — imported to surface the RuntimeError early at import time if needed
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared EncryptedBytes instance (stateless; safe to reuse across calls)
# ---------------------------------------------------------------------------
_ENC = EncryptedBytes()


def _encrypt(value: Any) -> bytes | None:
    """Encrypt a value through the EncryptedBytes TypeDecorator.

    Returns None if value is None (preserves NULL semantics).
    Raises RuntimeError if no DEK is set (fail-closed per T-16-28).
    """
    return _ENC.process_bind_param(value, None)


# ---------------------------------------------------------------------------
# Transaction dedup columns list (matches migration 022 BYTEA columns)
# ---------------------------------------------------------------------------
# Columns that get encrypted before INSERT
_TX_ENCRYPTED_COLS = (
    "tx_hash", "receipt_id", "direction", "counterparty", "action_type",
    "method_name", "amount", "fee", "token_id", "success", "raw_data",
)

# Columns that are cleartext (routing / non-PII)
_TX_CLEARTEXT_COLS = (
    "user_id", "wallet_id", "chain", "block_height", "block_timestamp", "created_at",
)

_TX_UPSERT_SQL = """
INSERT INTO transactions (
    user_id, wallet_id, tx_hash, receipt_id, chain,
    direction, counterparty, action_type, method_name,
    amount, fee, token_id,
    block_height, block_timestamp,
    success, raw_data,
    tx_dedup_hmac
) VALUES (
    %(user_id)s, %(wallet_id)s, %(tx_hash)s, %(receipt_id)s, %(chain)s,
    %(direction)s, %(counterparty)s, %(action_type)s, %(method_name)s,
    %(amount)s, %(fee)s, %(token_id)s,
    %(block_height)s, %(block_timestamp)s,
    %(success)s, %(raw_data)s,
    %(tx_dedup_hmac)s
)
ON CONFLICT (user_id, tx_dedup_hmac) DO UPDATE SET
    tx_hash         = EXCLUDED.tx_hash,
    receipt_id      = EXCLUDED.receipt_id,
    direction       = EXCLUDED.direction,
    counterparty    = EXCLUDED.counterparty,
    action_type     = EXCLUDED.action_type,
    method_name     = EXCLUDED.method_name,
    amount          = EXCLUDED.amount,
    fee             = EXCLUDED.fee,
    token_id        = EXCLUDED.token_id,
    block_height    = EXCLUDED.block_height,
    block_timestamp = EXCLUDED.block_timestamp,
    success         = EXCLUDED.success,
    raw_data        = EXCLUDED.raw_data
RETURNING id
"""


def insert_transaction_with_dedup(conn, **columns) -> int | None:
    """INSERT into transactions with tx_dedup_hmac computed from chain+tx_hash+receipt_id+wallet_id.

    All in-scope columns are encrypted through EncryptedBytes before binding.
    Uses ON CONFLICT (user_id, tx_dedup_hmac) DO UPDATE for idempotent upserts.

    Args:
        conn: psycopg2 connection. Must be within caller's transaction boundary.
        **columns: keyword arguments matching Transaction column names.
            Required: user_id, wallet_id, chain, tx_hash.
            Optional but encrypted if present: receipt_id, direction, counterparty,
            action_type, method_name, amount, fee, token_id, success, raw_data.
            Optional cleartext: block_height, block_timestamp.

    Returns:
        The inserted/updated row id, or None if the query returned no row.

    Raises:
        RuntimeError: if no DEK is set in the current context.
        KeyError: if required columns (user_id, wallet_id, chain, tx_hash) are missing.
    """
    # Compute dedup HMAC — uses plaintext values before encryption
    tx_dedup_hmac = compute_tx_dedup_hmac(
        chain=columns["chain"],
        tx_hash=columns.get("tx_hash") or "",
        receipt_id=columns.get("receipt_id") or "",
        wallet_id=columns["wallet_id"],
    )

    # Build parameter dict — encrypt all in-scope columns
    params = {
        # Cleartext routing columns
        "user_id": columns["user_id"],
        "wallet_id": columns["wallet_id"],
        "chain": columns["chain"],
        "block_height": columns.get("block_height"),
        "block_timestamp": columns.get("block_timestamp"),
        # Dedup HMAC (cleartext BYTEA)
        "tx_dedup_hmac": tx_dedup_hmac,
        # Encrypted columns
        "tx_hash": _encrypt(columns.get("tx_hash")),
        "receipt_id": _encrypt(columns.get("receipt_id")),
        "direction": _encrypt(columns.get("direction")),
        "counterparty": _encrypt(columns.get("counterparty")),
        "action_type": _encrypt(columns.get("action_type")),
        "method_name": _encrypt(columns.get("method_name")),
        "amount": _encrypt(columns.get("amount")),
        "fee": _encrypt(columns.get("fee")),
        "token_id": _encrypt(columns.get("token_id")),
        "success": _encrypt(columns.get("success")),
        "raw_data": _encrypt(columns.get("raw_data")),
    }

    cur = conn.cursor()
    cur.execute(_TX_UPSERT_SQL, params)
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# ACB snapshot dedup columns (matches migration 022 BYTEA columns)
# ---------------------------------------------------------------------------
_ACB_UPSERT_SQL = """
INSERT INTO acb_snapshots (
    user_id, token_symbol, classification_id, block_timestamp,
    event_type, units_delta, units_after, cost_cad_delta, total_cost_cad,
    acb_per_unit_cad, proceeds_cad, gain_loss_cad,
    price_usd, price_cad, price_estimated, needs_review,
    acb_dedup_hmac
) VALUES (
    %(user_id)s, %(token_symbol)s, %(classification_id)s, %(block_timestamp)s,
    %(event_type)s, %(units_delta)s, %(units_after)s, %(cost_cad_delta)s, %(total_cost_cad)s,
    %(acb_per_unit_cad)s, %(proceeds_cad)s, %(gain_loss_cad)s,
    %(price_usd)s, %(price_cad)s, %(price_estimated)s, %(needs_review)s,
    %(acb_dedup_hmac)s
)
ON CONFLICT (user_id, acb_dedup_hmac) DO UPDATE SET
    token_symbol     = EXCLUDED.token_symbol,
    block_timestamp  = EXCLUDED.block_timestamp,
    event_type       = EXCLUDED.event_type,
    units_delta      = EXCLUDED.units_delta,
    units_after      = EXCLUDED.units_after,
    cost_cad_delta   = EXCLUDED.cost_cad_delta,
    total_cost_cad   = EXCLUDED.total_cost_cad,
    acb_per_unit_cad = EXCLUDED.acb_per_unit_cad,
    proceeds_cad     = EXCLUDED.proceeds_cad,
    gain_loss_cad    = EXCLUDED.gain_loss_cad,
    price_usd        = EXCLUDED.price_usd,
    price_cad        = EXCLUDED.price_cad,
    price_estimated  = EXCLUDED.price_estimated,
    needs_review     = EXCLUDED.needs_review,
    updated_at       = NOW()
RETURNING id
"""


def insert_acb_snapshot_with_dedup(conn, **columns) -> int | None:
    """INSERT into acb_snapshots with acb_dedup_hmac computed from user_id+token_symbol+classification_id.

    All in-scope columns are encrypted through EncryptedBytes before binding.
    Uses ON CONFLICT (user_id, acb_dedup_hmac) DO UPDATE for idempotent upserts.

    Args:
        conn: psycopg2 connection. Must be within caller's transaction boundary.
        **columns: keyword arguments matching ACBSnapshot column names.
            Required: user_id, token_symbol, classification_id, block_timestamp,
            event_type, units_delta, units_after, cost_cad_delta, total_cost_cad,
            acb_per_unit_cad, price_estimated.
            Optional: proceeds_cad, gain_loss_cad, price_usd, price_cad, needs_review.

    Returns:
        The inserted/updated row id, or None if the query returned no row.

    Raises:
        RuntimeError: if no DEK is set in the current context.
        KeyError: if required columns are missing.
    """
    # Compute dedup HMAC — uses plaintext token_symbol before encryption
    acb_dedup_hmac = compute_acb_dedup_hmac(
        user_id=columns["user_id"],
        token_symbol=columns["token_symbol"],
        classification_id=columns["classification_id"],
    )

    params = {
        # Cleartext routing columns
        "user_id": columns["user_id"],
        "classification_id": columns["classification_id"],
        "block_timestamp": columns["block_timestamp"],
        "needs_review": columns.get("needs_review", False),
        # Dedup HMAC (cleartext BYTEA)
        "acb_dedup_hmac": acb_dedup_hmac,
        # Encrypted columns
        "token_symbol": _encrypt(columns["token_symbol"]),
        "event_type": _encrypt(columns["event_type"]),
        "units_delta": _encrypt(columns["units_delta"]),
        "units_after": _encrypt(columns["units_after"]),
        "cost_cad_delta": _encrypt(columns["cost_cad_delta"]),
        "total_cost_cad": _encrypt(columns["total_cost_cad"]),
        "acb_per_unit_cad": _encrypt(columns["acb_per_unit_cad"]),
        "proceeds_cad": _encrypt(columns.get("proceeds_cad")),
        "gain_loss_cad": _encrypt(columns.get("gain_loss_cad")),
        "price_usd": _encrypt(columns.get("price_usd")),
        "price_cad": _encrypt(columns.get("price_cad")),
        "price_estimated": _encrypt(columns.get("price_estimated", False)),
    }

    cur = conn.cursor()
    cur.execute(_ACB_UPSERT_SQL, params)
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None
