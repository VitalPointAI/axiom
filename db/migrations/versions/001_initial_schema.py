"""Initial PostgreSQL schema for Axiom/NearTax.

Creates all Phase 1 tables with proper PostgreSQL types:
  - SERIAL (autoincrement) primary keys
  - NUMERIC for financial values (no precision loss)
  - JSONB for raw transaction data
  - TIMESTAMPTZ (DateTime with timezone) for all timestamps
  - CHECK constraints for enum-like columns
  - user_id FK on all data tables for multi-user isolation
  - chain column on wallets/transactions for multi-chain extensibility

Revision ID: 001
Revises: (none — initial migration)
Create Date: 2026-03-12 00:00:00 UTC
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("near_account_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("near_account_id", name="uq_users_near_account_id"),
    )

    # ------------------------------------------------------------------
    # wallets
    # ------------------------------------------------------------------
    op.create_table(
        "wallets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(128), nullable=False),
        sa.Column("chain", sa.String(20), nullable=False, server_default="near"),
        sa.Column("label", sa.String(256), nullable=True),
        sa.Column("is_owned", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_wallets_user_id"),
        sa.PrimaryKeyConstraint("id", name="pk_wallets"),
        sa.UniqueConstraint(
            "user_id", "account_id", "chain",
            name="uq_wallet_user_account_chain",
        ),
    )
    op.create_index("ix_wallets_user_id", "wallets", ["user_id"])

    # ------------------------------------------------------------------
    # transactions
    # ------------------------------------------------------------------
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column("tx_hash", sa.String(128), nullable=False),
        sa.Column("receipt_id", sa.String(128), nullable=True),
        sa.Column("chain", sa.String(20), nullable=False, server_default="near"),
        sa.Column("direction", sa.String(3), nullable=True),
        sa.Column("counterparty", sa.String(128), nullable=True),
        sa.Column("action_type", sa.String(64), nullable=True),
        sa.Column("method_name", sa.String(128), nullable=True),
        sa.Column("amount", sa.Numeric(40, 0), nullable=True),
        sa.Column("fee", sa.Numeric(40, 0), nullable=True),
        sa.Column("token_id", sa.String(128), nullable=True),
        sa.Column("block_height", sa.BigInteger(), nullable=True),
        sa.Column("block_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("direction IN ('in', 'out')", name="ck_tx_direction"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_transactions_user_id"),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], name="fk_transactions_wallet_id"),
        sa.PrimaryKeyConstraint("id", name="pk_transactions"),
        sa.UniqueConstraint(
            "chain", "tx_hash", "receipt_id", "wallet_id",
            name="uq_tx_chain_hash_receipt_wallet",
        ),
    )
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"])
    op.create_index("ix_transactions_wallet_id", "transactions", ["wallet_id"])
    op.create_index("ix_transactions_chain", "transactions", ["chain"])
    op.create_index("ix_transactions_block_timestamp", "transactions", ["block_timestamp"])

    # ------------------------------------------------------------------
    # indexing_jobs
    # ------------------------------------------------------------------
    op.create_table(
        "indexing_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("chain", sa.String(20), nullable=False, server_default="near"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cursor", sa.String(256), nullable=True),
        sa.Column("progress_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed','retrying')",
            name="ck_job_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_jobs_user_id"),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], name="fk_jobs_wallet_id"),
        sa.PrimaryKeyConstraint("id", name="pk_indexing_jobs"),
    )
    op.create_index("ix_indexing_jobs_user_id", "indexing_jobs", ["user_id"])
    op.create_index("ix_indexing_jobs_wallet_id", "indexing_jobs", ["wallet_id"])
    op.create_index("ix_indexing_jobs_status", "indexing_jobs", ["status"])

    # ------------------------------------------------------------------
    # staking_events
    # ------------------------------------------------------------------
    op.create_table(
        "staking_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column("validator_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=True),
        sa.Column("amount", sa.Numeric(40, 0), nullable=True),
        sa.Column("amount_near", sa.Numeric(24, 8), nullable=True),
        sa.Column("fmv_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("fmv_cad", sa.Numeric(18, 8), nullable=True),
        sa.Column("epoch_id", sa.BigInteger(), nullable=True),
        sa.Column("block_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("tx_hash", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('deposit','withdraw','reward')",
            name="ck_staking_event_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_staking_user_id"),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], name="fk_staking_wallet_id"),
        sa.PrimaryKeyConstraint("id", name="pk_staking_events"),
    )
    op.create_index("ix_staking_events_user_id", "staking_events", ["user_id"])
    op.create_index("ix_staking_events_wallet_id", "staking_events", ["wallet_id"])
    op.create_index("ix_staking_events_block_timestamp", "staking_events", ["block_timestamp"])

    # ------------------------------------------------------------------
    # epoch_snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "epoch_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column("validator_id", sa.String(128), nullable=False),
        sa.Column("epoch_id", sa.BigInteger(), nullable=False),
        sa.Column("staked_balance", sa.Numeric(40, 0), nullable=False),
        sa.Column("unstaked_balance", sa.Numeric(40, 0), nullable=False, server_default="0"),
        sa.Column("epoch_timestamp", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_epoch_user_id"),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], name="fk_epoch_wallet_id"),
        sa.PrimaryKeyConstraint("id", name="pk_epoch_snapshots"),
        sa.UniqueConstraint(
            "wallet_id", "validator_id", "epoch_id",
            name="uq_epoch_wallet_validator_epoch",
        ),
    )
    op.create_index("ix_epoch_snapshots_user_id", "epoch_snapshots", ["user_id"])
    op.create_index("ix_epoch_snapshots_wallet_id", "epoch_snapshots", ["wallet_id"])

    # ------------------------------------------------------------------
    # price_cache
    # ------------------------------------------------------------------
    op.create_table(
        "price_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("coin_id", sa.String(64), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("price", sa.Numeric(24, 10), nullable=False),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_price_cache"),
        sa.UniqueConstraint("coin_id", "date", "currency", name="uq_price_coin_date_currency"),
    )
    op.create_index("ix_price_cache_coin_date", "price_cache", ["coin_id", "date"])

    # ------------------------------------------------------------------
    # lockup_events
    # ------------------------------------------------------------------
    op.create_table(
        "lockup_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column("lockup_account_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(40, 0), nullable=True),
        sa.Column("amount_near", sa.Numeric(24, 8), nullable=True),
        sa.Column("fmv_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("fmv_cad", sa.Numeric(18, 8), nullable=True),
        sa.Column("block_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("tx_hash", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_lockup_user_id"),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], name="fk_lockup_wallet_id"),
        sa.PrimaryKeyConstraint("id", name="pk_lockup_events"),
    )
    op.create_index("ix_lockup_events_user_id", "lockup_events", ["user_id"])
    op.create_index("ix_lockup_events_wallet_id", "lockup_events", ["wallet_id"])
    op.create_index("ix_lockup_events_block_timestamp", "lockup_events", ["block_timestamp"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("lockup_events")
    op.drop_table("price_cache")
    op.drop_table("epoch_snapshots")
    op.drop_table("staking_events")
    op.drop_table("indexing_jobs")
    op.drop_table("transactions")
    op.drop_table("wallets")
    op.drop_table("users")
