"""Phase 16 migration 022 integration tests.

Tests the Alembic migration 022_pqe_schema upgrade and downgrade against a
real PostgreSQL database. These tests are gated behind the RUN_MIGRATION_TESTS
environment variable to avoid requiring a spare Postgres in routine unit test runs.

To run locally:
  export RUN_MIGRATION_TESTS=1
  export TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/axiom_test_022
  pytest tests/test_migration_022.py -v

To run in CI (GitHub Actions / Docker):
  Set RUN_MIGRATION_TESTS=1 and TEST_DATABASE_URL in the CI environment.
  The test database MUST be a throwaway — migration 022 TRUNCATEs user-data tables.

Coverage:
  - test_022_upgrade_preserves_user_wipes_data:
      - users row preserved (D-22)
      - email_hmac and near_account_id_hmac populated (64-char hex)
      - transactions TRUNCATEd (D-20)
      - wallets TRUNCATEd (D-21)
      - session_dek_cache table created and empty (D-26)
      - accountant_access.rewrapped_client_dek column exists (D-25)
      - transactions.tx_dedup_hmac column exists with UNIQUE on (user_id, tx_dedup_hmac) (D-28)
      - mlkem_ek / mlkem_sealed_dk / wrapped_dek columns exist and are NULL
      - worker_key_enabled is FALSE by default

  - test_022_downgrade_removes_scaffolding:
      - session_dek_cache table is gone
      - users.mlkem_ek column is gone
      - users.email is back to VARCHAR type (TEXT/character varying)

  - test_022_env_var_required:
      - Upgrade with missing EMAIL_HMAC_KEY raises RuntimeError (fail-fast guard)
"""

import os
import subprocess

import pytest
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Skip gate — requires RUN_MIGRATION_TESTS=1 AND TEST_DATABASE_URL
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MIGRATION_TESTS") != "1",
    reason=(
        "Migration tests require a disposable Postgres. "
        "Set RUN_MIGRATION_TESTS=1 and TEST_DATABASE_URL=postgresql://... to enable."
    ),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_test_db_url() -> str:
    """Return the test database URL.

    Uses TEST_DATABASE_URL env var. Fails loudly if not set so the engineer
    knows exactly what to configure.
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL environment variable is not set. "
            "Set it to a throwaway Postgres database URL "
            "(e.g. postgresql://user:pass@localhost:5432/axiom_test_022) "
            "before running migration tests."
        )
    return url


def _run_alembic(target: str, db_url: str) -> None:
    """Run alembic upgrade/downgrade against the given DB URL.

    Uses subprocess to ensure Alembic reads the real alembic.ini + env.py
    from the project root, just as it would in production.
    """
    result = subprocess.run(
        ["alembic", "-x", f"db_url={db_url}", target],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # project root
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic {target} failed:\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )


def _col_exists(conn: sa.engine.Connection, table: str, column: str) -> bool:
    """Return True if the column exists in the table (information_schema query)."""
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).fetchone()
    return row is not None


def _table_exists(conn: sa.engine.Connection, table: str) -> bool:
    """Return True if the table exists."""
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = :t"
        ),
        {"t": table},
    ).fetchone()
    return row is not None


def _col_data_type(conn: sa.engine.Connection, table: str, column: str) -> str | None:
    """Return the data_type string for a column, or None if not found."""
    row = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).fetchone()
    return row[0] if row else None


def _constraint_exists(
    conn: sa.engine.Connection,
    table: str,
    constraint_name: str,
    constraint_type: str = "UNIQUE",
) -> bool:
    """Return True if the named constraint exists on the table."""
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name = :t AND constraint_name = :cn "
            "AND constraint_type = :ct"
        ),
        {"t": table, "cn": constraint_name, "ct": constraint_type},
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_url() -> str:
    """Module-scoped DB URL. Used by all tests in this module."""
    return _get_test_db_url()


@pytest.fixture()
def migrated_db_at_021(db_url: str, monkeypatch: pytest.MonkeyPatch):
    """Set required env vars, migrate the test DB to exactly revision 021, seed data.

    Teardown: run alembic downgrade base to leave the DB clean for the next run.
    """
    # Set all required PQE env vars so migration 022 can compute HMACs
    monkeypatch.setenv("EMAIL_HMAC_KEY", "00" * 32)
    monkeypatch.setenv("NEAR_ACCOUNT_HMAC_KEY", "11" * 32)
    monkeypatch.setenv("TX_DEDUP_KEY", "22" * 32)
    monkeypatch.setenv("ACB_DEDUP_KEY", "33" * 32)
    monkeypatch.setenv("SESSION_DEK_WRAP_KEY", "44" * 32)

    # Start from a clean slate by downgrading to base
    _run_alembic("downgrade base", db_url)

    # Migrate to 021 (the revision immediately before 022)
    _run_alembic("upgrade 021", db_url)

    # Seed test data: one user with email + near_account_id, one wallet, one transaction
    engine = sa.create_engine(db_url)
    with engine.begin() as conn:
        # Insert a test user with email and near_account_id (cleartext at revision 021)
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, near_account_id, username, created_at) "
                "VALUES (9001, 'alice@example.com', 'alice.near', 'alice', NOW())"
            )
        )
        # Insert a wallet row (will be TRUNCATEd by migration 022)
        conn.execute(
            sa.text(
                "INSERT INTO wallets (user_id, account_id, chain, label, is_owned, created_at) "
                "VALUES (9001, 'alice.near', 'near', 'Main wallet', TRUE, NOW())"
            )
        )
        # Insert a transaction row (will be TRUNCATEd by migration 022)
        conn.execute(
            sa.text(
                "INSERT INTO transactions "
                "(user_id, wallet_id, tx_hash, chain, direction, counterparty, "
                " action_type, amount, block_height, block_timestamp, created_at) "
                "VALUES (9001, "
                "  (SELECT id FROM wallets WHERE user_id=9001 LIMIT 1), "
                "  'abc123def456', 'near', 'in', 'bob.near', "
                "  'transfer', 1000000000000000000000000, 100000, 1700000000000000000, NOW())"
            )
        )

    yield db_url

    # Teardown: clean up by downgrading to base
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS session_dek_cache"))

    try:
        _run_alembic("downgrade base", db_url)
    except Exception:
        pass  # Best-effort cleanup — don't fail the test on teardown errors

    engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_022_upgrade_preserves_user_wipes_data(migrated_db_at_021: str) -> None:
    """Running alembic upgrade 022 must:
    - Keep the users row (D-22 auth table preservation)
    - Populate email_hmac from existing email (D-05)
    - Populate near_account_id_hmac from existing near_account_id (D-24)
    - TRUNCATE transactions and wallets (D-20, D-21)
    - Create session_dek_cache table (D-26)
    - Add accountant_access.rewrapped_client_dek (D-25)
    - Add transactions.tx_dedup_hmac with UNIQUE constraint (D-28)
    - Add ML-KEM envelope columns on users (D-11, D-12)
    - worker_key_enabled defaults to FALSE (D-17)
    """
    db_url = migrated_db_at_021

    # Run the upgrade
    _run_alembic("upgrade 022", db_url)

    engine = sa.create_engine(db_url)
    with engine.begin() as conn:
        # D-22: users row preserved
        user_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM users WHERE id = 9001")
        ).scalar()
        assert user_count == 1, "users row must survive the migration (D-22)"

        # D-05/D-24: HMAC surrogates populated
        row = conn.execute(
            sa.text("SELECT email_hmac, near_account_id_hmac FROM users WHERE id = 9001")
        ).fetchone()
        assert row is not None, "users row disappeared post-migration"
        email_hmac, near_account_id_hmac = row
        assert email_hmac is not None, "email_hmac must be populated from pre-migration email"
        assert len(email_hmac) == 64, f"email_hmac must be 64-char hex, got len={len(email_hmac)}"
        assert near_account_id_hmac is not None, "near_account_id_hmac must be populated"
        assert len(near_account_id_hmac) == 64, "near_account_id_hmac must be 64-char hex"

        # D-11/D-12: ML-KEM columns exist (NULL until provisioned by auth-service)
        assert _col_exists(conn, "users", "mlkem_ek"), "users.mlkem_ek must exist"
        assert _col_exists(conn, "users", "mlkem_sealed_dk"), "users.mlkem_sealed_dk must exist"
        assert _col_exists(conn, "users", "wrapped_dek"), "users.wrapped_dek must exist"

        mlkem_row = conn.execute(
            sa.text("SELECT mlkem_ek, mlkem_sealed_dk, wrapped_dek FROM users WHERE id = 9001")
        ).fetchone()
        assert mlkem_row[0] is None, "mlkem_ek must be NULL until provisioned"
        assert mlkem_row[1] is None, "mlkem_sealed_dk must be NULL until provisioned"
        assert mlkem_row[2] is None, "wrapped_dek must be NULL until provisioned"

        # D-17: worker_key_enabled defaults to FALSE
        wk_enabled = conn.execute(
            sa.text("SELECT worker_key_enabled FROM users WHERE id = 9001")
        ).scalar()
        assert wk_enabled is False, "worker_key_enabled must default to FALSE"

        # D-20/D-21: user-data tables TRUNCATEd
        tx_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM transactions")
        ).scalar()
        assert tx_count == 0, f"transactions must be empty after migration, got {tx_count}"

        wallet_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM wallets")
        ).scalar()
        assert wallet_count == 0, f"wallets must be empty after migration, got {wallet_count}"

        # D-26: session_dek_cache table exists
        assert _table_exists(conn, "session_dek_cache"), "session_dek_cache table must exist"

        cache_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM session_dek_cache")
        ).scalar()
        assert cache_count == 0, "session_dek_cache must start empty"

        # D-25: accountant_access.rewrapped_client_dek column
        assert _col_exists(conn, "accountant_access", "rewrapped_client_dek"), \
            "accountant_access.rewrapped_client_dek must exist (D-25)"

        # D-28: transactions.tx_dedup_hmac column and UNIQUE constraint
        assert _col_exists(conn, "transactions", "tx_dedup_hmac"), \
            "transactions.tx_dedup_hmac must exist (D-28)"
        assert _constraint_exists(conn, "transactions", "uq_tx_user_dedup_hmac"), \
            "uq_tx_user_dedup_hmac UNIQUE constraint must exist (D-28)"

        # D-28: acb_snapshots.acb_dedup_hmac column
        assert _col_exists(conn, "acb_snapshots", "acb_dedup_hmac"), \
            "acb_snapshots.acb_dedup_hmac must exist (D-28)"
        assert _constraint_exists(conn, "acb_snapshots", "uq_acb_user_dedup"), \
            "uq_acb_user_dedup UNIQUE constraint must exist (D-28)"

        # D-02/D-03: encrypted column types on transactions are BYTEA
        tx_hash_type = _col_data_type(conn, "transactions", "tx_hash")
        assert tx_hash_type == "bytea", \
            f"transactions.tx_hash must be bytea post-migration, got {tx_hash_type}"

        # D-03: wallets.account_id is BYTEA
        acct_id_type = _col_data_type(conn, "wallets", "account_id")
        assert acct_id_type == "bytea", \
            f"wallets.account_id must be bytea, got {acct_id_type}"

        # D-04: public data plane tables untouched (account_transactions still exists)
        assert _table_exists(conn, "account_transactions"), \
            "account_transactions (public data plane) must be untouched (D-04)"
        assert _table_exists(conn, "block_heights"), \
            "block_heights (public data plane) must be untouched (D-04)"

    engine.dispose()


def test_022_downgrade_removes_scaffolding(migrated_db_at_021: str) -> None:
    """After upgrade 022 + downgrade 021:
    - session_dek_cache table is gone
    - users.mlkem_ek column is gone
    - users.email is back to character varying (not BYTEA)
    """
    db_url = migrated_db_at_021

    # Upgrade first
    _run_alembic("upgrade 022", db_url)

    # Then downgrade back to 021
    _run_alembic("downgrade 021", db_url)

    engine = sa.create_engine(db_url)
    with engine.begin() as conn:
        # session_dek_cache table removed
        assert not _table_exists(conn, "session_dek_cache"), \
            "session_dek_cache must be dropped by downgrade 021"

        # users.mlkem_ek column removed
        assert not _col_exists(conn, "users", "mlkem_ek"), \
            "users.mlkem_ek must be dropped by downgrade 021"

        # users.mlkem_sealed_dk column removed
        assert not _col_exists(conn, "users", "mlkem_sealed_dk"), \
            "users.mlkem_sealed_dk must be dropped by downgrade 021"

        # users.email is back to character varying (VARCHAR/TEXT)
        email_type = _col_data_type(conn, "users", "email")
        assert email_type is not None, "users.email must exist after downgrade"
        assert email_type in ("character varying", "text"), \
            f"users.email must be character varying after downgrade, got {email_type}"

        # users.near_account_id is back to character varying
        aid_type = _col_data_type(conn, "users", "near_account_id")
        assert aid_type is not None, "users.near_account_id must exist after downgrade"
        assert aid_type in ("character varying", "text"), \
            f"users.near_account_id must be character varying after downgrade, got {aid_type}"

        # accountant_access.rewrapped_client_dek column removed
        assert not _col_exists(conn, "accountant_access", "rewrapped_client_dek"), \
            "accountant_access.rewrapped_client_dek must be dropped by downgrade 021"

        # transactions.tx_dedup_hmac column removed
        assert not _col_exists(conn, "transactions", "tx_dedup_hmac"), \
            "transactions.tx_dedup_hmac must be dropped by downgrade 021"

    engine.dispose()


def test_022_env_var_required(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """If EMAIL_HMAC_KEY is missing, upgrade 022 must raise RuntimeError and abort.

    This tests the fail-fast guard in _compute_email_hmac() — migration must
    refuse to run without the HMAC key rather than silently writing NULL HMACs.
    """
    # Ensure EMAIL_HMAC_KEY is NOT set
    monkeypatch.delenv("EMAIL_HMAC_KEY", raising=False)
    monkeypatch.setenv("NEAR_ACCOUNT_HMAC_KEY", "11" * 32)
    monkeypatch.setenv("TX_DEDUP_KEY", "22" * 32)
    monkeypatch.setenv("ACB_DEDUP_KEY", "33" * 32)
    monkeypatch.setenv("SESSION_DEK_WRAP_KEY", "44" * 32)

    # Start from revision 021
    _run_alembic("downgrade base", db_url)
    _run_alembic("upgrade 021", db_url)

    # Attempt upgrade 022 WITHOUT EMAIL_HMAC_KEY — should fail
    result = subprocess.run(
        ["alembic", "-x", f"db_url={db_url}", "upgrade 022"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env={**os.environ, "EMAIL_HMAC_KEY": ""},  # empty string should also fail
    )
    # Migration should exit non-zero and mention the missing key
    assert result.returncode != 0, \
        "upgrade 022 must fail if EMAIL_HMAC_KEY is not set"

    # Clean up: bring back to base
    try:
        _run_alembic("downgrade base", db_url)
    except Exception:
        pass
