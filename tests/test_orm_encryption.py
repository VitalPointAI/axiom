"""ORM encryption round-trip tests (Phase 16 Plan 05).

Tests that EncryptedBytes TypeDecorator correctly:
  1. Encrypts data at write time (ciphertext != plaintext in raw DB)
  2. Decrypts data at read time (ORM returns original plaintext)
  3. Rejects reads with a different DEK (InvalidTag)
  4. Rejects reads with no DEK (RuntimeError)
  5. tx_dedup_hmac prevents duplicate transactions
  6. User isolation: DEK from user A cannot decrypt user B's rows

DB-backed tests require a real PostgreSQL at migration 022.
Gate them with RUN_MIGRATION_TESTS=1 + TEST_DATABASE_URL.

To run:
    export RUN_MIGRATION_TESTS=1
    export TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/axiom_test
    export TX_DEDUP_KEY=$(openssl rand -hex 32)
    export ACB_DEDUP_KEY=$(openssl rand -hex 32)
    pytest tests/test_orm_encryption.py -v
"""

import os
from decimal import Decimal

import pytest

from cryptography.exceptions import InvalidTag

from db.crypto import (
    EncryptedBytes,
    compute_tx_dedup_hmac,
    set_dek,
    zero_dek,
)

# ---------------------------------------------------------------------------
# Skip gate for DB-backed tests
# ---------------------------------------------------------------------------

_NEEDS_DB = pytest.mark.skipif(
    os.environ.get("RUN_MIGRATION_TESTS") != "1",
    reason=(
        "DB round-trip tests require migration 022 schema. "
        "Set RUN_MIGRATION_TESTS=1 and TEST_DATABASE_URL=postgresql://... to enable."
    ),
)


# ---------------------------------------------------------------------------
# DB fixture
# ---------------------------------------------------------------------------

def _get_test_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL must be set when RUN_MIGRATION_TESTS=1"
        )
    return url


@pytest.fixture(scope="function")
def pg_conn():
    """Raw psycopg2 connection to a test DB at migration 022."""
    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 not available")

    url = _get_test_db_url()
    conn = psycopg2.connect(url)
    conn.autocommit = False
    yield conn
    # Rollback any uncommitted changes after each test
    try:
        conn.rollback()
    except Exception:
        pass
    conn.close()


@pytest.fixture(autouse=True)
def _zero_dek():
    """Zero the DEK before and after each test."""
    zero_dek()
    yield
    zero_dek()


# ---------------------------------------------------------------------------
# Helper: insert a Transaction row directly via the dedup helper
# ---------------------------------------------------------------------------

def _insert_tx(conn, *, user_id=1, wallet_id=1, chain="near",
               tx_hash="0xABCDEF123", receipt_id="rcpt_001",
               direction="in", counterparty="alice.near",
               amount=Decimal("1000000000000000000000000"),
               success=True, raw_data=None):
    """Insert one transaction row using insert_transaction_with_dedup."""
    from db.dedup_hmac_helpers import insert_transaction_with_dedup
    tx_id = insert_transaction_with_dedup(
        conn,
        user_id=user_id,
        wallet_id=wallet_id,
        tx_hash=tx_hash,
        receipt_id=receipt_id,
        chain=chain,
        direction=direction,
        counterparty=counterparty,
        amount=amount,
        fee=Decimal("0"),
        token_id=None,
        block_height=12345,
        block_timestamp=1700000000,
        success=success,
        raw_data=raw_data,
    )
    conn.commit()
    return tx_id


def _insert_acb(conn, *, user_id=1, token_symbol="NEAR", classification_id=1,
                block_timestamp=1700000000):
    """Insert one acb_snapshots row using insert_acb_snapshot_with_dedup."""
    from db.dedup_hmac_helpers import insert_acb_snapshot_with_dedup
    snap_id = insert_acb_snapshot_with_dedup(
        conn,
        user_id=user_id,
        token_symbol=token_symbol,
        classification_id=classification_id,
        block_timestamp=block_timestamp,
        event_type="acquire",
        units_delta=Decimal("10.0"),
        units_after=Decimal("10.0"),
        cost_cad_delta=Decimal("100.00"),
        total_cost_cad=Decimal("100.00"),
        acb_per_unit_cad=Decimal("10.00"),
        proceeds_cad=None,
        gain_loss_cad=None,
        price_usd=Decimal("5.00"),
        price_cad=Decimal("6.75"),
        price_estimated=False,
        needs_review=False,
    )
    conn.commit()
    return snap_id


# ---------------------------------------------------------------------------
# Test: round-trip — write encrypted, read back same plaintext
# ---------------------------------------------------------------------------

@_NEEDS_DB
def test_transaction_roundtrip(pg_conn):
    """Write a Transaction row; read it back; plaintext values match original."""
    import psycopg2  # noqa: F401
    import sqlalchemy as sa
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.orm import Session

    dek = b"\x01" * 32
    set_dek(dek)

    try:
        tx_id = _insert_tx(pg_conn, user_id=1, wallet_id=1, tx_hash="roundtrip_hash",
                            counterparty="bob.near", amount=Decimal("999"))

        assert tx_id is not None, "Expected an inserted row id"

        # Verify raw DB: BYTEA column should NOT be the plaintext string
        cur = pg_conn.cursor()
        cur.execute(
            "SELECT tx_hash, counterparty, amount FROM transactions WHERE id = %s",
            (tx_id,),
        )
        row = cur.fetchone()
        cur.close()
        assert row is not None, "Row not found"
        raw_tx_hash, raw_counterparty, raw_amount = row

        # Ciphertext must be bytes (not a string) and must differ from plaintext
        raw_tx_hash_bytes = bytes(raw_tx_hash) if raw_tx_hash else b""
        assert raw_tx_hash_bytes != b"roundtrip_hash", \
            "tx_hash was stored as plaintext — encryption not applied"
        # Must start with nonce (12 bytes) + ciphertext, total > 29 bytes
        assert len(raw_tx_hash_bytes) >= 1 + 12 + 16, \
            f"tx_hash ciphertext too short: {len(raw_tx_hash_bytes)} bytes"

        # Read via ORM with correct DEK → should return original plaintext
        url = _get_test_db_url()
        engine = sa.create_engine(url, poolclass=StaticPool, connect_args={"options": "-c timezone=UTC"})
        with Session(engine) as s:
            from db.models._all_models import Transaction
            tx = s.get(Transaction, tx_id)
            assert tx is not None, "Transaction not found via ORM"
            assert tx.tx_hash == "roundtrip_hash", f"Got: {tx.tx_hash!r}"
            assert tx.counterparty == "bob.near", f"Got: {tx.counterparty!r}"
        engine.dispose()

    finally:
        zero_dek()
        try:
            pg_conn.execute("DELETE FROM transactions WHERE id = %s", (tx_id,)) if tx_id else None
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()


# ---------------------------------------------------------------------------
# Test: wrong DEK raises InvalidTag
# ---------------------------------------------------------------------------

@_NEEDS_DB
def test_wrong_dek_rejects(pg_conn):
    """Read a row encrypted with DEK-A using DEK-B should raise InvalidTag."""
    import sqlalchemy as sa
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.orm import Session

    dek_a = b"\x01" * 32
    dek_b = b"\x02" * 32

    set_dek(dek_a)
    tx_id = None
    try:
        tx_id = _insert_tx(pg_conn, user_id=1, wallet_id=1, tx_hash="wrong_dek_test")
    finally:
        zero_dek()

    url = _get_test_db_url()
    engine = sa.create_engine(url, poolclass=StaticPool, connect_args={"options": "-c timezone=UTC"})

    try:
        # Read with wrong DEK — should raise InvalidTag
        set_dek(dek_b)
        with Session(engine) as s:
            from db.models._all_models import Transaction
            tx = s.get(Transaction, tx_id)
            with pytest.raises(InvalidTag):
                # Accessing the encrypted attribute triggers decryption
                _ = tx.tx_hash
    finally:
        zero_dek()
        engine.dispose()
        try:
            pg_conn.cursor().execute("DELETE FROM transactions WHERE id = %s", (tx_id,))
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()


# ---------------------------------------------------------------------------
# Test: missing DEK raises RuntimeError (fail-closed — T-16-28)
# ---------------------------------------------------------------------------

@_NEEDS_DB
def test_missing_dek_read(pg_conn):
    """READ with no DEK set should raise RuntimeError (fail-closed)."""
    import sqlalchemy as sa
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.orm import Session

    dek = b"\x03" * 32
    set_dek(dek)
    tx_id = None
    try:
        tx_id = _insert_tx(pg_conn, user_id=1, wallet_id=1, tx_hash="no_dek_read_test")
    finally:
        zero_dek()

    url = _get_test_db_url()
    engine = sa.create_engine(url, poolclass=StaticPool, connect_args={"options": "-c timezone=UTC"})

    try:
        # No DEK set — accessing encrypted attribute should raise RuntimeError
        # (zero_dek already called above, and autouse fixture zeroes before yield)
        with Session(engine) as s:
            from db.models._all_models import Transaction
            tx = s.get(Transaction, tx_id)
            with pytest.raises(RuntimeError, match="No DEK in context"):
                _ = tx.tx_hash
    finally:
        engine.dispose()
        try:
            pg_conn.cursor().execute("DELETE FROM transactions WHERE id = %s", (tx_id,))
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()


# ---------------------------------------------------------------------------
# Test: tx_dedup_hmac prevents duplicate insertion (ON CONFLICT)
# ---------------------------------------------------------------------------

@_NEEDS_DB
def test_tx_dedup_hmac_prevents_duplicate(pg_conn):
    """Inserting the same transaction twice results in exactly 1 row."""
    import psycopg2  # noqa: F401

    dek = b"\x04" * 32
    set_dek(dek)

    try:
        # Insert twice with identical dedup keys (same wallet_id + tx_hash + receipt_id + chain)
        tx_id_1 = _insert_tx(pg_conn, user_id=1, wallet_id=1,
                              tx_hash="dedup_test_hash", receipt_id="dedup_rcpt",
                              chain="near", amount=Decimal("100"))

        tx_id_2 = _insert_tx(pg_conn, user_id=1, wallet_id=1,
                              tx_hash="dedup_test_hash", receipt_id="dedup_rcpt",
                              chain="near", amount=Decimal("200"))  # updated amount

        # Both inserts should return an id (the second is an update)
        assert tx_id_1 is not None
        assert tx_id_2 is not None

        # Count rows with this dedup key
        expected_hmac = compute_tx_dedup_hmac(
            chain="near",
            tx_hash="dedup_test_hash",
            receipt_id="dedup_rcpt",
            wallet_id=1,
        )
        cur = pg_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id = 1 AND tx_dedup_hmac = %s",
            (expected_hmac,),
        )
        count = cur.fetchone()[0]
        cur.close()
        assert count == 1, f"Expected 1 row after dedup, got {count}"

    finally:
        zero_dek()
        try:
            pg_conn.cursor().execute(
                "DELETE FROM transactions WHERE user_id = 1 AND tx_dedup_hmac = %s",
                (compute_tx_dedup_hmac(chain="near", tx_hash="dedup_test_hash",
                                        receipt_id="dedup_rcpt", wallet_id=1),),
            )
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()


# ---------------------------------------------------------------------------
# Test: user isolation — DEK-A cannot decrypt user-B rows
# ---------------------------------------------------------------------------

@_NEEDS_DB
def test_user_isolation(pg_conn):
    """DEK for user A cannot decrypt rows encrypted for user B."""
    import sqlalchemy as sa
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.orm import Session

    dek_a = b"\xAA" * 32
    dek_b = b"\xBB" * 32

    # Insert row for user A (wallet_id=1)
    set_dek(dek_a)
    tx_id_a = None
    try:
        tx_id_a = _insert_tx(pg_conn, user_id=1, wallet_id=1,
                              tx_hash="user_a_tx", chain="near")
    finally:
        zero_dek()

    # Insert row for user B (user_id=2, wallet_id=2 — assumed to exist or use id=999)
    # If wallet_id=2 doesn't exist, we skip the user-B insert and only test
    # that reading user-A's row with user-B's DEK raises InvalidTag.
    url = _get_test_db_url()
    engine = sa.create_engine(url, poolclass=StaticPool, connect_args={"options": "-c timezone=UTC"})

    try:
        # Try to read user-A's row using user-B's DEK — should raise InvalidTag
        set_dek(dek_b)
        with Session(engine) as s:
            from db.models._all_models import Transaction
            tx = s.get(Transaction, tx_id_a)
            assert tx is not None, "Expected row to exist"
            with pytest.raises(InvalidTag):
                _ = tx.tx_hash
    finally:
        zero_dek()
        engine.dispose()
        try:
            pg_conn.cursor().execute("DELETE FROM transactions WHERE id = %s", (tx_id_a,))
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()


# ---------------------------------------------------------------------------
# Test: missing DEK on WRITE raises RuntimeError (pure Python — no DB needed)
# ---------------------------------------------------------------------------

def test_missing_dek_write_raises():
    """EncryptedBytes.process_bind_param raises RuntimeError when no DEK set."""
    # _zero_dek autouse fixture ensures no DEK is set
    enc = EncryptedBytes()
    with pytest.raises(RuntimeError, match="No DEK in context"):
        enc.process_bind_param("some secret value", None)


# ---------------------------------------------------------------------------
# Test: EncryptedBytes round-trip (pure Python — no DB needed)
# ---------------------------------------------------------------------------

def test_encrypted_bytes_roundtrip_pure():
    """EncryptedBytes encrypt/decrypt round-trip without DB."""
    dek = b"\x05" * 32
    set_dek(dek)
    try:
        enc = EncryptedBytes()
        original = "hello encrypted world"
        ciphertext = enc.process_bind_param(original, None)
        assert isinstance(ciphertext, bytes)
        assert ciphertext != original.encode("utf-8")

        plaintext = enc.process_result_value(ciphertext, None)
        assert plaintext == original
    finally:
        zero_dek()
