"""Audit log encryption tests (Phase 16 Plan 05).

Tests that db/audit.write_audit():
  1. Requires a DEK to be set in context (raises RuntimeError if missing)
  2. Round-trip: old_value and new_value are ciphertext in the DB when
     written via write_audit(); ORM reads them back as the original dicts.

The missing-DEK test (test_audit_write_requires_dek) is pure Python and
runs on every test suite invocation.

The round-trip test requires a real PostgreSQL at migration 022 and is
gated with RUN_MIGRATION_TESTS=1.
"""

import os
from unittest.mock import MagicMock

import pytest

from db.crypto import set_dek, zero_dek

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


@pytest.fixture(autouse=True)
def _zero_dek():
    """Ensure DEK is zeroed before and after each test."""
    zero_dek()
    yield
    zero_dek()


# ---------------------------------------------------------------------------
# Test: missing DEK raises RuntimeError (pure Python — no DB)
# ---------------------------------------------------------------------------

def test_audit_write_requires_dek():
    """write_audit() raises RuntimeError when no DEK is set in context.

    This is the fail-closed invariant (T-16-30): audit_log columns are
    EncryptedBytes, so writes without a DEK must be blocked loudly.
    """
    from db.audit import write_audit

    # No DEK set (autouse fixture zeroes it)
    mock_conn = MagicMock()

    with pytest.raises(RuntimeError, match="audit_log write attempted without a DEK in context"):
        write_audit(
            mock_conn,
            user_id=1,
            entity_type="transaction_classification",
            entity_id=42,
            action="initial_classify",
            new_value={"category": "capital_gain", "confidence": 0.95},
            actor_type="system",
        )

    # Verify no actual DB call was made (RuntimeError should fire before conn access)
    mock_conn.cursor.assert_not_called()


# ---------------------------------------------------------------------------
# Test: write_audit skips when conn=None even with DEK set
# ---------------------------------------------------------------------------

def test_audit_write_conn_none_with_dek():
    """write_audit(conn=None, ...) returns silently when DEK IS set.

    conn=None is used in tests that don't provision a DB; the DEK preflight
    runs first (so it's fail-closed), but if a DEK is present, it should
    not error — just skip the actual insert.
    """
    from db.audit import write_audit

    dek = b"\x01" * 32
    set_dek(dek)

    # Should not raise — conn=None means skip the insert
    write_audit(
        None,
        user_id=1,
        entity_type="transaction_classification",
        entity_id=1,
        action="initial_classify",
        new_value={"category": "transfer", "confidence": 1.0},
        actor_type="system",
    )


# ---------------------------------------------------------------------------
# Test: audit round-trip (DB-backed)
# ---------------------------------------------------------------------------

@_NEEDS_DB
def test_audit_roundtrip(pg_conn):
    """write_audit encrypts old_value/new_value; ORM read returns original dicts."""
    import psycopg2  # noqa: F401
    import sqlalchemy as sa
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from db.audit import write_audit

    dek = b"\x06" * 32
    set_dek(dek)

    old_val = {"category": "transfer", "confidence": 0.8}
    new_val = {"category": "capital_gain", "confidence": 0.95}
    audit_id = None

    try:
        cur = pg_conn.cursor()
        # Get a cursor context — write_audit uses a savepoint
        write_audit(
            pg_conn,
            user_id=1,
            entity_type="transaction_classification",
            entity_id=99,
            action="reclassify",
            old_value=old_val,
            new_value=new_val,
            actor_type="user",
            notes="test round-trip",
        )
        pg_conn.commit()

        # Fetch the audit_id just inserted
        cur.execute(
            "SELECT id FROM audit_log ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        audit_id = row[0] if row else None
        cur.close()
        assert audit_id is not None, "Audit row was not inserted"

        # Verify raw DB: old_value column should be BYTEA ciphertext, not JSON text
        cur = pg_conn.cursor()
        cur.execute(
            "SELECT old_value, new_value FROM audit_log WHERE id = %s",
            (audit_id,),
        )
        raw_row = cur.fetchone()
        cur.close()
        assert raw_row is not None, "Audit row missing from raw query"
        raw_old, raw_new = raw_row

        # Ciphertext should be bytes, not the original JSON text
        raw_old_bytes = bytes(raw_old) if raw_old else b""
        assert raw_old_bytes != b'{"category": "transfer", "confidence": 0.8}', \
            "old_value was stored as plaintext — encryption not applied"
        assert len(raw_old_bytes) > 29, \
            f"old_value ciphertext too short: {len(raw_old_bytes)} bytes"

        # Read via ORM with correct DEK — should return original dicts
        url = _get_db_url()
        engine = sa.create_engine(url, poolclass=StaticPool, connect_args={"options": "-c timezone=UTC"})
        with Session(engine) as s:
            from db.models._all_models import AuditLog
            log = s.get(AuditLog, audit_id)
            assert log is not None, "AuditLog not found via ORM"
            # old_value was stored as a JSON dict → should round-trip as dict
            assert log.old_value == old_val, f"Got: {log.old_value!r}"
            assert log.new_value == new_val, f"Got: {log.new_value!r}"
        engine.dispose()

    finally:
        zero_dek()
        try:
            if audit_id:
                pg_conn.cursor().execute("DELETE FROM audit_log WHERE id = %s", (audit_id,))
                pg_conn.commit()
        except Exception:
            pg_conn.rollback()


def _get_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("TEST_DATABASE_URL must be set when RUN_MIGRATION_TESTS=1")
    return url


# ---------------------------------------------------------------------------
# DB fixture (same pattern as test_orm_encryption.py)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def pg_conn():
    """Raw psycopg2 connection to a test DB at migration 022."""
    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 not available")

    url = _get_db_url()
    conn = psycopg2.connect(url)
    conn.autocommit = False
    yield conn
    try:
        conn.rollback()
    except Exception:
        pass
    conn.close()
