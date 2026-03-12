"""Phase 4 cost basis schema.

Creates tables for ACB (Adjusted Cost Base) tracking, capital gains reporting,
income ledger, and minute-level price caching:
  - acb_snapshots: per-transaction ACB state machine snapshots
  - capital_gains_ledger: one row per disposal event with gain/loss detail
  - income_ledger: one row per income event (staking, vesting, airdrop)
  - price_cache_minute: minute-level price data separate from daily price_cache

Revision ID: 004
Revises: 003
Create Date: 2026-03-12 00:00:00 UTC
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # acb_snapshots — per-transaction ACB state
    # ------------------------------------------------------------------
    op.create_table(
        "acb_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_symbol", sa.String(32), nullable=False),
        sa.Column("classification_id", sa.Integer(), nullable=False),
        sa.Column("block_timestamp", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("units_delta", sa.Numeric(24, 8), nullable=False),
        sa.Column("units_after", sa.Numeric(24, 8), nullable=False),
        sa.Column("cost_cad_delta", sa.Numeric(24, 8), nullable=False),
        sa.Column("total_cost_cad", sa.Numeric(24, 8), nullable=False),
        sa.Column("acb_per_unit_cad", sa.Numeric(24, 8), nullable=False),
        sa.Column("proceeds_cad", sa.Numeric(24, 8), nullable=True),
        sa.Column("gain_loss_cad", sa.Numeric(24, 8), nullable=True),
        sa.Column("price_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("price_cad", sa.Numeric(18, 8), nullable=True),
        sa.Column(
            "price_estimated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "needs_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
            "event_type IN ('acquire', 'dispose')",
            name="ck_acb_event_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_acb_user_id"),
        sa.ForeignKeyConstraint(
            ["classification_id"],
            ["transaction_classifications.id"],
            name="fk_acb_classification_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_acb_snapshots"),
        sa.UniqueConstraint(
            "user_id",
            "token_symbol",
            "classification_id",
            name="uq_acb_user_token_classification",
        ),
    )
    op.create_index("ix_acb_user_id", "acb_snapshots", ["user_id"])
    op.create_index("ix_acb_token_symbol", "acb_snapshots", ["token_symbol"])
    op.create_index("ix_acb_block_timestamp", "acb_snapshots", ["block_timestamp"])

    # ------------------------------------------------------------------
    # capital_gains_ledger — one row per disposal
    # ------------------------------------------------------------------
    op.create_table(
        "capital_gains_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("acb_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("token_symbol", sa.String(32), nullable=False),
        sa.Column("disposal_date", sa.Date(), nullable=False),
        sa.Column("block_timestamp", sa.BigInteger(), nullable=False),
        sa.Column("units_disposed", sa.Numeric(24, 8), nullable=False),
        sa.Column("proceeds_cad", sa.Numeric(24, 8), nullable=False),
        sa.Column("acb_used_cad", sa.Numeric(24, 8), nullable=False),
        sa.Column(
            "fees_cad",
            sa.Numeric(24, 8),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("gain_loss_cad", sa.Numeric(24, 8), nullable=False),
        sa.Column(
            "is_superficial_loss",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("denied_loss_cad", sa.Numeric(24, 8), nullable=True),
        sa.Column(
            "needs_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("tax_year", sa.SmallInteger(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_cgl_user_id"),
        sa.ForeignKeyConstraint(
            ["acb_snapshot_id"],
            ["acb_snapshots.id"],
            name="fk_cgl_acb_snapshot_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_capital_gains_ledger"),
        sa.UniqueConstraint("acb_snapshot_id", name="uq_cgl_acb_snapshot_id"),
    )
    op.create_index("ix_cgl_user_id", "capital_gains_ledger", ["user_id"])
    op.create_index("ix_cgl_tax_year", "capital_gains_ledger", ["tax_year"])
    op.create_index("ix_cgl_token_symbol", "capital_gains_ledger", ["token_symbol"])

    # ------------------------------------------------------------------
    # income_ledger — one row per income event
    # ------------------------------------------------------------------
    op.create_table(
        "income_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("staking_event_id", sa.Integer(), nullable=True),
        sa.Column("lockup_event_id", sa.Integer(), nullable=True),
        sa.Column("classification_id", sa.Integer(), nullable=True),
        sa.Column("token_symbol", sa.String(32), nullable=False),
        sa.Column("income_date", sa.Date(), nullable=False),
        sa.Column("block_timestamp", sa.BigInteger(), nullable=False),
        sa.Column("units_received", sa.Numeric(24, 8), nullable=False),
        sa.Column("fmv_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("fmv_cad", sa.Numeric(18, 8), nullable=False),
        sa.Column("acb_added_cad", sa.Numeric(24, 8), nullable=False),
        sa.Column("tax_year", sa.SmallInteger(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_il_user_id"),
        sa.ForeignKeyConstraint(
            ["staking_event_id"],
            ["staking_events.id"],
            name="fk_il_staking_event_id",
        ),
        sa.ForeignKeyConstraint(
            ["lockup_event_id"],
            ["lockup_events.id"],
            name="fk_il_lockup_event_id",
        ),
        sa.ForeignKeyConstraint(
            ["classification_id"],
            ["transaction_classifications.id"],
            name="fk_il_classification_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_income_ledger"),
    )
    op.create_index("ix_il_user_id", "income_ledger", ["user_id"])
    op.create_index("ix_il_tax_year", "income_ledger", ["tax_year"])
    op.create_index("ix_il_source_type", "income_ledger", ["source_type"])

    # ------------------------------------------------------------------
    # price_cache_minute — minute-level price data
    # ------------------------------------------------------------------
    op.create_table(
        "price_cache_minute",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("coin_id", sa.String(64), nullable=False),
        sa.Column("unix_ts", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("price", sa.Numeric(24, 10), nullable=False),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column(
            "is_estimated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_price_cache_minute"),
        sa.UniqueConstraint(
            "coin_id", "unix_ts", "currency", name="uq_pcm_coin_ts_currency"
        ),
    )
    op.create_index("ix_pcm_coin_ts", "price_cache_minute", ["coin_id", "unix_ts"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("price_cache_minute")
    op.drop_table("income_ledger")
    op.drop_table("capital_gains_ledger")
    op.drop_table("acb_snapshots")
