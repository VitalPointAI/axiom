"""Phase 16: Post-quantum envelope encryption schema.

Revision ID: 022
Revises: 021
Create Date: 2026-04-12

Implements D-20 through D-28 of Phase 16 (post-quantum-encryption-at-rest).

CRITICAL: This migration TRUNCATEs all user-data tables (D-20).
Run scripts/pre_pqe_backup.sh BEFORE this migration.
Restore via scripts/pqe_rollback.sh if needed.

Auth tables (users, passkeys, sessions, challenges, magic_link_tokens,
accountant_access) are PRESERVED per D-22. Users do not lose their accounts
or passkeys — they lose indexed data and must re-import after upgrade.

Decisions implemented:
  D-20: Re-import from source — wipe user-data tables, users re-run indexing
  D-21: wallets wiped, users re-enter via onboarding wizard
  D-22: auth tables preserved — passkeys, sessions, etc. untouched
  D-23: VitalPoint data goes through same migration (back up first)
  D-24: near_account_id_hmac surrogate UNIQUE column (D-24)
  D-25: accountant_access.rewrapped_client_dek column
  D-26: session_dek_cache table for auth-service → FastAPI DEK IPC
  D-28: tx_dedup_hmac / acb_dedup_hmac surrogate UNIQUE columns
"""

from __future__ import annotations

import hashlib
import hmac as stdlib_hmac
import os

import sqlalchemy as sa
from alembic import op

# Alembic revision chain
revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Tables whose user-scoped rows must be wiped (D-20)
# ---------------------------------------------------------------------------
# Note: account_transactions, account_dictionary, account_block_index_v2,
# block_heights, price_cache*, supported_exchanges, exchange_connections,
# file_imports are NOT in this list per D-04 and migration notes.

_TABLES_TO_TRUNCATE = [
    "transactions",
    "wallets",
    "staking_events",
    "lockup_events",
    "epoch_snapshots",
    "transaction_classifications",
    "acb_snapshots",
    "capital_gains_ledger",
    "income_ledger",
    "verification_results",
    "account_verification_status",
    "audit_log",
    "indexing_jobs",
]


# ---------------------------------------------------------------------------
# HMAC backfill helpers (run BEFORE dropping plaintext columns)
# ---------------------------------------------------------------------------

def _compute_email_hmac(conn: sa.engine.Connection) -> None:
    """Populate users.email_hmac from existing plaintext users.email.

    Uses stdlib hmac (not pgcrypto) so no DB extension dependency.
    Parameterized queries — no f-string logging of email values (T-16-26).
    """
    key_hex = os.environ.get("EMAIL_HMAC_KEY")
    if not key_hex:
        raise RuntimeError(
            "EMAIL_HMAC_KEY not set in environment. "
            "Set EMAIL_HMAC_KEY=<64 hex chars> before running alembic upgrade 022. "
            "Migration aborted — no data has been modified."
        )
    key = bytes.fromhex(key_hex)
    rows = conn.execute(
        sa.text("SELECT id, email FROM users WHERE email IS NOT NULL")
    ).fetchall()
    for uid, email in rows:
        digest = stdlib_hmac.new(
            key, email.lower().strip().encode("utf-8"), hashlib.sha256
        ).hexdigest()
        conn.execute(
            sa.text("UPDATE users SET email_hmac = :h WHERE id = :i"),
            {"h": digest, "i": uid},
        )


def _compute_near_account_hmac(conn: sa.engine.Connection) -> None:
    """Populate users.near_account_id_hmac from existing plaintext near_account_id.

    D-24: cleartext UNIQUE surrogate so auth-service can look up an Axiom
    user row by NEAR account id before the session DEK is available.
    """
    key_hex = os.environ.get("NEAR_ACCOUNT_HMAC_KEY")
    if not key_hex:
        raise RuntimeError(
            "NEAR_ACCOUNT_HMAC_KEY not set in environment. "
            "Set NEAR_ACCOUNT_HMAC_KEY=<64 hex chars> before running alembic upgrade 022. "
            "Migration aborted — no data has been modified."
        )
    key = bytes.fromhex(key_hex)
    rows = conn.execute(
        sa.text("SELECT id, near_account_id FROM users WHERE near_account_id IS NOT NULL")
    ).fetchall()
    for uid, account_id in rows:
        digest = stdlib_hmac.new(
            key, account_id.lower().strip().encode("utf-8"), hashlib.sha256
        ).hexdigest()
        conn.execute(
            sa.text("UPDATE users SET near_account_id_hmac = :h WHERE id = :i"),
            {"h": digest, "i": uid},
        )


# ---------------------------------------------------------------------------
# Column-swap helpers (drop+re-add as BYTEA; tables are empty after TRUNCATE)
# ---------------------------------------------------------------------------

def _swap_columns(
    table: str,
    cols: list[tuple[str, sa.types.TypeEngine]],
) -> None:
    """Drop each named column then re-add as LargeBinary (BYTEA).

    Safe to call only AFTER the table has been TRUNCATEd — there is no
    in-place data conversion; column type changes from cleartext to ciphertext.
    """
    for name, _ in cols:
        op.drop_column(table, name)
    for name, _ in cols:
        op.add_column(table, sa.Column(name, sa.LargeBinary, nullable=True))


def _restore_columns(
    table: str,
    cols: list[tuple[str, sa.types.TypeEngine]],
) -> None:
    """Drop BYTEA column and re-add with original type (for downgrade).

    Restores schema shape only — data restore requires pg_restore from backup.
    """
    for name, _ in cols:
        op.drop_column(table, name)
    for name, orig_type in cols:
        op.add_column(table, sa.Column(name, orig_type, nullable=True))


# ---------------------------------------------------------------------------
# upgrade()
# ---------------------------------------------------------------------------

def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------ #
    # 1. users — add PQE columns before touching plaintext columns         #
    # ------------------------------------------------------------------ #
    op.add_column("users", sa.Column("mlkem_ek", sa.LargeBinary, nullable=True))
    op.add_column("users", sa.Column("mlkem_sealed_dk", sa.LargeBinary, nullable=True))
    op.add_column("users", sa.Column("wrapped_dek", sa.LargeBinary, nullable=True))
    op.add_column("users", sa.Column("email_hmac", sa.Text, nullable=True))
    op.add_column("users", sa.Column("near_account_id_hmac", sa.Text, nullable=True))
    op.add_column("users", sa.Column("worker_sealed_dek", sa.LargeBinary, nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "worker_key_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Backfill HMAC surrogates from existing plaintext BEFORE dropping source columns
    _compute_email_hmac(conn)
    _compute_near_account_hmac(conn)

    # Drop old UNIQUE constraints on plaintext columns (Postgres auto-names them)
    # Using try/except approach via if_exists=True to be defensive across envs
    op.drop_index("ix_users_email", table_name="users", if_exists=True)
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.drop_constraint("users_near_account_id_key", "users", type_="unique")

    # Add UNIQUE constraints on the HMAC surrogate columns (D-24)
    op.create_unique_constraint("uq_users_email_hmac", "users", ["email_hmac"])
    op.create_unique_constraint(
        "uq_users_near_account_id_hmac", "users", ["near_account_id_hmac"]
    )

    # Drop plaintext columns; re-add as BYTEA (ciphertext holders).
    # D-22: users rows are preserved — only the column types change.
    # username has no HMAC needed (not a lookup key).
    op.drop_column("users", "email")
    op.drop_column("users", "near_account_id")
    op.drop_column("users", "username")
    op.add_column("users", sa.Column("email", sa.LargeBinary, nullable=True))
    op.add_column("users", sa.Column("near_account_id", sa.LargeBinary, nullable=True))
    op.add_column("users", sa.Column("username", sa.LargeBinary, nullable=True))

    # ------------------------------------------------------------------ #
    # 2. accountant_access — add rewrapped DEK column (D-25)               #
    # ------------------------------------------------------------------ #
    op.add_column(
        "accountant_access",
        sa.Column("rewrapped_client_dek", sa.LargeBinary, nullable=True),
    )

    # ------------------------------------------------------------------ #
    # 3. session_dek_cache — new table for auth-service → FastAPI IPC (D-26) #
    # ------------------------------------------------------------------ #
    op.create_table(
        "session_dek_cache",
        sa.Column("session_id", sa.Text, primary_key=True),
        sa.Column("encrypted_dek", sa.LargeBinary, nullable=False),
        sa.Column(
            "expires_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Note: REFERENCES sessions(id) ON DELETE CASCADE would be ideal but
        # Axiom's sessions table id is TEXT PK — that FK is application-enforced.
        # auth-service calls DELETE on logout; rows also expire via expires_at.
    )
    op.create_index(
        "ix_session_dek_cache_expires",
        "session_dek_cache",
        ["expires_at"],
    )

    # ------------------------------------------------------------------ #
    # 4. TRUNCATE user-data tables (D-20)                                  #
    # ------------------------------------------------------------------ #
    # CASCADE handles FK chains (classifications → transactions, etc.).
    # account_transactions, account_dictionary, account_block_index_v2,
    # block_heights, price_cache* are NOT touched (D-04 / D-18).
    truncate_list = ", ".join(_TABLES_TO_TRUNCATE)
    op.execute(f"TRUNCATE TABLE {truncate_list} RESTART IDENTITY CASCADE;")

    # User-scoped classification/spam rules are also wiped (system rules kept)
    op.execute("DELETE FROM classification_rules WHERE user_id IS NOT NULL;")
    op.execute("DELETE FROM spam_rules WHERE user_id IS NOT NULL;")

    # ------------------------------------------------------------------ #
    # 5. Swap encrypted columns on per-user tables (now empty, cheap)      #
    # ------------------------------------------------------------------ #

    # transactions
    _swap_columns(
        "transactions",
        [
            ("tx_hash", sa.String(128)),
            ("receipt_id", sa.String(128)),
            ("direction", sa.String(8)),
            ("counterparty", sa.String(128)),
            ("action_type", sa.String(64)),
            ("method_name", sa.String(128)),
            ("amount", sa.Numeric(40, 0)),
            ("fee", sa.Numeric(40, 0)),
            ("token_id", sa.String(128)),
            ("success", sa.Boolean),
            ("raw_data", sa.JSON),
        ],
    )
    # tx_dedup_hmac (D-28): populate via compute_tx_dedup_hmac() at insert time
    # server_default placeholder ensures NOT NULL during DDL; removed immediately after
    op.add_column(
        "transactions",
        sa.Column(
            "tx_dedup_hmac",
            sa.LargeBinary,
            nullable=False,
            server_default=sa.text("'\\x00'::bytea"),
        ),
    )
    op.alter_column("transactions", "tx_dedup_hmac", server_default=None)
    op.drop_constraint(
        "uq_tx_chain_hash_receipt_wallet", "transactions", type_="unique"
    )
    op.create_unique_constraint(
        "uq_tx_user_dedup_hmac", "transactions", ["user_id", "tx_dedup_hmac"]
    )

    # wallets (D-21: wallet account_id encrypted; UNIQUE on account_id dropped per D-06)
    _swap_columns(
        "wallets",
        [
            ("account_id", sa.String(128)),
            ("label", sa.String(256)),
            ("is_owned", sa.Boolean),
        ],
    )
    # Drop the uq_wallet_user_account_chain constraint (cleartext account_id gone)
    op.drop_constraint(
        "uq_wallet_user_account_chain", "wallets", type_="unique"
    )

    # staking_events
    _swap_columns(
        "staking_events",
        [
            ("validator_id", sa.String(128)),
            ("event_type", sa.String(20)),
            ("amount", sa.Numeric(40, 0)),
            ("amount_near", sa.Numeric(24, 8)),
            ("fmv_usd", sa.Numeric(18, 8)),
            ("fmv_cad", sa.Numeric(18, 8)),
            ("tx_hash", sa.String(128)),
        ],
    )
    # Drop staking_events check constraint that references cleartext event_type
    op.drop_constraint("ck_staking_event_type", "staking_events", type_="check")

    # epoch_snapshots
    _swap_columns(
        "epoch_snapshots",
        [
            ("validator_id", sa.String(128)),
            ("staked_balance", sa.Numeric(40, 0)),
            ("unstaked_balance", sa.Numeric(40, 0)),
        ],
    )
    # Drop unique constraint that references cleartext validator_id
    op.drop_constraint(
        "uq_epoch_wallet_validator_epoch", "epoch_snapshots", type_="unique"
    )

    # lockup_events
    _swap_columns(
        "lockup_events",
        [
            ("lockup_account_id", sa.String(128)),
            ("event_type", sa.String(32)),
            ("amount", sa.Numeric(40, 0)),
            ("amount_near", sa.Numeric(24, 8)),
            ("fmv_usd", sa.Numeric(18, 8)),
            ("fmv_cad", sa.Numeric(18, 8)),
            ("tx_hash", sa.String(128)),
        ],
    )

    # transaction_classifications
    _swap_columns(
        "transaction_classifications",
        [
            ("category", sa.String(50)),
            ("confidence", sa.Numeric(4, 3)),
            ("classification_source", sa.String(20)),
            ("fmv_usd", sa.Numeric(18, 8)),
            ("fmv_cad", sa.Numeric(18, 8)),
            ("notes", sa.Text),
        ],
    )
    # Drop check constraint referencing cleartext category / leg_type values
    # (category column is now BYTEA; leg_type stays cleartext and its check stands)
    op.drop_index("ix_tc_category", table_name="transaction_classifications")
    op.drop_index("ix_tc_needs_review", table_name="transaction_classifications")

    # acb_snapshots
    _swap_columns(
        "acb_snapshots",
        [
            ("token_symbol", sa.String(32)),
            ("event_type", sa.String(20)),
            ("units_delta", sa.Numeric(24, 8)),
            ("units_after", sa.Numeric(24, 8)),
            ("cost_cad_delta", sa.Numeric(24, 8)),
            ("total_cost_cad", sa.Numeric(24, 8)),
            ("acb_per_unit_cad", sa.Numeric(24, 8)),
            ("proceeds_cad", sa.Numeric(24, 8)),
            ("gain_loss_cad", sa.Numeric(24, 8)),
            ("price_usd", sa.Numeric(18, 8)),
            ("price_cad", sa.Numeric(18, 8)),
            ("price_estimated", sa.Boolean),
        ],
    )
    # Drop ACB check constraint and old unique constraint (cleartext columns gone)
    op.drop_constraint("ck_acb_event_type", "acb_snapshots", type_="check")
    op.add_column(
        "acb_snapshots",
        sa.Column(
            "acb_dedup_hmac",
            sa.LargeBinary,
            nullable=False,
            server_default=sa.text("'\\x00'::bytea"),
        ),
    )
    op.alter_column("acb_snapshots", "acb_dedup_hmac", server_default=None)
    op.drop_constraint(
        "uq_acb_user_token_classification", "acb_snapshots", type_="unique"
    )
    op.drop_index("ix_acb_token_symbol", table_name="acb_snapshots")
    op.create_unique_constraint(
        "uq_acb_user_dedup", "acb_snapshots", ["user_id", "acb_dedup_hmac"]
    )

    # capital_gains_ledger
    _swap_columns(
        "capital_gains_ledger",
        [
            ("token_symbol", sa.String(32)),
            ("units_disposed", sa.Numeric(24, 8)),
            ("proceeds_cad", sa.Numeric(24, 8)),
            ("acb_used_cad", sa.Numeric(24, 8)),
            ("fees_cad", sa.Numeric(24, 8)),
            ("gain_loss_cad", sa.Numeric(24, 8)),
            ("is_superficial_loss", sa.Boolean),
            ("denied_loss_cad", sa.Numeric(24, 8)),
        ],
    )
    op.drop_index("ix_cgl_token_symbol", table_name="capital_gains_ledger")

    # income_ledger
    _swap_columns(
        "income_ledger",
        [
            ("token_symbol", sa.String(32)),
            ("units_received", sa.Numeric(24, 8)),
            ("fmv_usd", sa.Numeric(18, 8)),
            ("fmv_cad", sa.Numeric(18, 8)),
            ("acb_added_cad", sa.Numeric(24, 8)),
        ],
    )

    # verification_results
    _swap_columns(
        "verification_results",
        [
            ("expected_balance_acb", sa.Numeric(24, 8)),
            ("expected_balance_replay", sa.Numeric(24, 8)),
            ("actual_balance", sa.Numeric(24, 8)),
            ("manual_balance", sa.Numeric(24, 8)),
            ("difference", sa.Numeric(24, 8)),
            ("onchain_liquid", sa.Numeric(24, 8)),
            ("onchain_locked", sa.Numeric(24, 8)),
            ("onchain_staked", sa.Numeric(24, 8)),
            ("diagnosis_detail", sa.Text),
            ("notes", sa.Text),
            ("rpc_error", sa.Text),
            ("diagnosis_category", sa.String(50)),
            ("diagnosis_confidence", sa.Numeric(4, 3)),
        ],
    )
    # Drop unique constraint referencing cleartext token_symbol (from uq_vr_wallet_token)
    op.drop_constraint("uq_vr_wallet_token", "verification_results", type_="unique")
    op.drop_index("ix_vr_status", table_name="verification_results")

    # account_verification_status
    _swap_columns("account_verification_status", [("notes", sa.Text)])
    op.drop_constraint("ck_avs_status", "account_verification_status", type_="check")

    # audit_log — fully encrypted per phase 16 privacy stance
    _swap_columns(
        "audit_log",
        [
            ("old_value", sa.JSON),
            ("new_value", sa.JSON),
            ("notes", sa.Text),
            ("entity_type", sa.String(50)),
            ("action", sa.String(50)),
        ],
    )
    # Drop indexes referencing cleartext entity_type / action columns
    op.drop_index("ix_al_entity", table_name="audit_log")
    op.drop_index("ix_al_action", table_name="audit_log")

    # ------------------------------------------------------------------ #
    # 6. classification_rules + spam_rules — parallel BYTEA columns        #
    # ------------------------------------------------------------------ #
    # System rules (user_id IS NULL) keep their cleartext columns.
    # User-scoped rules use the *_enc BYTEA columns.
    # ORM decides which to populate based on user_id at write time.
    op.add_column(
        "classification_rules",
        sa.Column("pattern_enc", sa.LargeBinary, nullable=True),
    )
    op.add_column(
        "classification_rules",
        sa.Column("category_enc", sa.LargeBinary, nullable=True),
    )
    op.add_column(
        "classification_rules",
        sa.Column("name_enc", sa.LargeBinary, nullable=True),
    )
    op.add_column(
        "spam_rules",
        sa.Column("rule_type_enc", sa.LargeBinary, nullable=True),
    )
    op.add_column(
        "spam_rules",
        sa.Column("value_enc", sa.LargeBinary, nullable=True),
    )


# ---------------------------------------------------------------------------
# downgrade()
# ---------------------------------------------------------------------------

def downgrade() -> None:
    """Restore schema shape to revision 021.

    IMPORTANT: This restores the COLUMN SHAPE only, not the data.
    The TRUNCATE in upgrade() is irreversible at the schema level.
    Data restore requires running scripts/pqe_rollback.sh which calls
    pg_restore from the pre_pqe_backup.sh dump taken before upgrade.
    """
    # ------------------------------------------------------------------ #
    # Remove parallel BYTEA columns on classification_rules / spam_rules   #
    # ------------------------------------------------------------------ #
    op.drop_column("spam_rules", "value_enc")
    op.drop_column("spam_rules", "rule_type_enc")
    op.drop_column("classification_rules", "name_enc")
    op.drop_column("classification_rules", "category_enc")
    op.drop_column("classification_rules", "pattern_enc")

    # ------------------------------------------------------------------ #
    # Restore per-user table column shapes (BYTEA → original types)        #
    # ------------------------------------------------------------------ #

    # audit_log
    op.create_index("ix_al_action", "audit_log", ["action"])
    op.create_index("ix_al_entity", "audit_log", ["entity_type", "entity_id"])
    _restore_columns(
        "audit_log",
        [
            ("old_value", sa.JSON),
            ("new_value", sa.JSON),
            ("notes", sa.Text),
            ("entity_type", sa.String(50)),
            ("action", sa.String(50)),
        ],
    )

    # account_verification_status
    op.execute(
        "ALTER TABLE account_verification_status "
        "ADD CONSTRAINT ck_avs_status CHECK "
        "(status IN ('verified', 'flagged', 'unverified'))"
    )
    _restore_columns("account_verification_status", [("notes", sa.Text)])

    # verification_results
    op.create_index("ix_vr_status", "verification_results", ["status"])
    op.create_unique_constraint(
        "uq_vr_wallet_token", "verification_results", ["wallet_id", "token_symbol"]
    )
    _restore_columns(
        "verification_results",
        [
            ("expected_balance_acb", sa.Numeric(24, 8)),
            ("expected_balance_replay", sa.Numeric(24, 8)),
            ("actual_balance", sa.Numeric(24, 8)),
            ("manual_balance", sa.Numeric(24, 8)),
            ("difference", sa.Numeric(24, 8)),
            ("onchain_liquid", sa.Numeric(24, 8)),
            ("onchain_locked", sa.Numeric(24, 8)),
            ("onchain_staked", sa.Numeric(24, 8)),
            ("diagnosis_detail", sa.Text),
            ("notes", sa.Text),
            ("rpc_error", sa.Text),
            ("diagnosis_category", sa.String(50)),
            ("diagnosis_confidence", sa.Numeric(4, 3)),
        ],
    )

    # income_ledger
    _restore_columns(
        "income_ledger",
        [
            ("token_symbol", sa.String(32)),
            ("units_received", sa.Numeric(24, 8)),
            ("fmv_usd", sa.Numeric(18, 8)),
            ("fmv_cad", sa.Numeric(18, 8)),
            ("acb_added_cad", sa.Numeric(24, 8)),
        ],
    )

    # capital_gains_ledger
    op.create_index("ix_cgl_token_symbol", "capital_gains_ledger", ["token_symbol"])
    _restore_columns(
        "capital_gains_ledger",
        [
            ("token_symbol", sa.String(32)),
            ("units_disposed", sa.Numeric(24, 8)),
            ("proceeds_cad", sa.Numeric(24, 8)),
            ("acb_used_cad", sa.Numeric(24, 8)),
            ("fees_cad", sa.Numeric(24, 8)),
            ("gain_loss_cad", sa.Numeric(24, 8)),
            ("is_superficial_loss", sa.Boolean),
            ("denied_loss_cad", sa.Numeric(24, 8)),
        ],
    )

    # acb_snapshots
    op.create_index("ix_acb_token_symbol", "acb_snapshots", ["token_symbol"])
    op.drop_constraint("uq_acb_user_dedup", "acb_snapshots", type_="unique")
    op.drop_column("acb_snapshots", "acb_dedup_hmac")
    op.create_unique_constraint(
        "uq_acb_user_token_classification",
        "acb_snapshots",
        ["user_id", "token_symbol", "classification_id"],
    )
    op.execute(
        "ALTER TABLE acb_snapshots "
        "ADD CONSTRAINT ck_acb_event_type CHECK "
        "(event_type IN ('acquire', 'dispose'))"
    )
    _restore_columns(
        "acb_snapshots",
        [
            ("token_symbol", sa.String(32)),
            ("event_type", sa.String(20)),
            ("units_delta", sa.Numeric(24, 8)),
            ("units_after", sa.Numeric(24, 8)),
            ("cost_cad_delta", sa.Numeric(24, 8)),
            ("total_cost_cad", sa.Numeric(24, 8)),
            ("acb_per_unit_cad", sa.Numeric(24, 8)),
            ("proceeds_cad", sa.Numeric(24, 8)),
            ("gain_loss_cad", sa.Numeric(24, 8)),
            ("price_usd", sa.Numeric(18, 8)),
            ("price_cad", sa.Numeric(18, 8)),
            ("price_estimated", sa.Boolean),
        ],
    )

    # transaction_classifications
    op.create_index(
        "ix_tc_needs_review",
        "transaction_classifications",
        ["needs_review"],
    )
    op.create_index(
        "ix_tc_category",
        "transaction_classifications",
        ["category"],
    )
    _restore_columns(
        "transaction_classifications",
        [
            ("category", sa.String(50)),
            ("confidence", sa.Numeric(4, 3)),
            ("classification_source", sa.String(20)),
            ("fmv_usd", sa.Numeric(18, 8)),
            ("fmv_cad", sa.Numeric(18, 8)),
            ("notes", sa.Text),
        ],
    )

    # lockup_events
    _restore_columns(
        "lockup_events",
        [
            ("lockup_account_id", sa.String(128)),
            ("event_type", sa.String(32)),
            ("amount", sa.Numeric(40, 0)),
            ("amount_near", sa.Numeric(24, 8)),
            ("fmv_usd", sa.Numeric(18, 8)),
            ("fmv_cad", sa.Numeric(18, 8)),
            ("tx_hash", sa.String(128)),
        ],
    )

    # epoch_snapshots
    op.create_unique_constraint(
        "uq_epoch_wallet_validator_epoch",
        "epoch_snapshots",
        ["wallet_id", "validator_id", "epoch_id"],
    )
    _restore_columns(
        "epoch_snapshots",
        [
            ("validator_id", sa.String(128)),
            ("staked_balance", sa.Numeric(40, 0)),
            ("unstaked_balance", sa.Numeric(40, 0)),
        ],
    )

    # staking_events
    op.execute(
        "ALTER TABLE staking_events "
        "ADD CONSTRAINT ck_staking_event_type CHECK "
        "(event_type IN ('deposit','withdraw','reward'))"
    )
    _restore_columns(
        "staking_events",
        [
            ("validator_id", sa.String(128)),
            ("event_type", sa.String(20)),
            ("amount", sa.Numeric(40, 0)),
            ("amount_near", sa.Numeric(24, 8)),
            ("fmv_usd", sa.Numeric(18, 8)),
            ("fmv_cad", sa.Numeric(18, 8)),
            ("tx_hash", sa.String(128)),
        ],
    )

    # wallets
    op.create_unique_constraint(
        "uq_wallet_user_account_chain",
        "wallets",
        ["user_id", "account_id", "chain"],
    )
    _restore_columns(
        "wallets",
        [
            ("account_id", sa.String(128)),
            ("label", sa.String(256)),
            ("is_owned", sa.Boolean),
        ],
    )

    # transactions
    op.drop_constraint("uq_tx_user_dedup_hmac", "transactions", type_="unique")
    op.drop_column("transactions", "tx_dedup_hmac")
    op.create_unique_constraint(
        "uq_tx_chain_hash_receipt_wallet",
        "transactions",
        ["chain", "tx_hash", "receipt_id", "wallet_id"],
    )
    _restore_columns(
        "transactions",
        [
            ("tx_hash", sa.String(128)),
            ("receipt_id", sa.String(128)),
            ("direction", sa.String(8)),
            ("counterparty", sa.String(128)),
            ("action_type", sa.String(64)),
            ("method_name", sa.String(128)),
            ("amount", sa.Numeric(40, 0)),
            ("fee", sa.Numeric(40, 0)),
            ("token_id", sa.String(128)),
            ("success", sa.Boolean),
            ("raw_data", sa.JSON),
        ],
    )

    # ------------------------------------------------------------------ #
    # Remove session_dek_cache table (D-26)                                #
    # ------------------------------------------------------------------ #
    op.drop_index("ix_session_dek_cache_expires", table_name="session_dek_cache")
    op.drop_table("session_dek_cache")

    # ------------------------------------------------------------------ #
    # Remove accountant_access.rewrapped_client_dek (D-25)                 #
    # ------------------------------------------------------------------ #
    op.drop_column("accountant_access", "rewrapped_client_dek")

    # ------------------------------------------------------------------ #
    # Restore users columns                                                #
    # ------------------------------------------------------------------ #
    # Remove BYTEA placeholders and PQE columns
    op.drop_column("users", "username")
    op.drop_column("users", "near_account_id")
    op.drop_column("users", "email")

    # Remove HMAC unique constraints
    op.drop_constraint("uq_users_near_account_id_hmac", "users", type_="unique")
    op.drop_constraint("uq_users_email_hmac", "users", type_="unique")

    # Remove PQE-specific columns
    op.drop_column("users", "worker_key_enabled")
    op.drop_column("users", "worker_sealed_dek")
    op.drop_column("users", "near_account_id_hmac")
    op.drop_column("users", "email_hmac")
    op.drop_column("users", "wrapped_dek")
    op.drop_column("users", "mlkem_sealed_dk")
    op.drop_column("users", "mlkem_ek")

    # Restore plaintext columns with original types and UNIQUE constraints
    op.add_column("users", sa.Column("email", sa.String(256), nullable=True))
    op.add_column("users", sa.Column("near_account_id", sa.String(128), nullable=True))
    op.add_column("users", sa.Column("username", sa.String(128), nullable=True))
    op.create_unique_constraint("users_email_key", "users", ["email"])
    op.create_unique_constraint("users_near_account_id_key", "users", ["near_account_id"])
    op.create_unique_constraint("users_username_key", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])
