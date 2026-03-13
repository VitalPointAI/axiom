"""Phase 5 verification schema.

Creates tables for balance reconciliation and account verification status:
  - verification_results: per-wallet verification run results with diagnosis
  - account_verification_status: per-wallet rollup status for UI dashboard

Revision ID: 005
Revises: 004
Create Date: 2026-03-13 00:00:00 UTC
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # verification_results — per-wallet verification run results
    # ------------------------------------------------------------------
    op.create_table(
        "verification_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column("chain", sa.String(20), nullable=False),
        sa.Column(
            "token_symbol", sa.String(32), nullable=False, server_default="NEAR"
        ),
        # Balance components (all in human units, Decimal precision)
        sa.Column("expected_balance_acb", sa.Numeric(24, 8), nullable=True),
        sa.Column("expected_balance_replay", sa.Numeric(24, 8), nullable=True),
        sa.Column("actual_balance", sa.Numeric(24, 8), nullable=True),
        sa.Column("manual_balance", sa.Numeric(24, 8), nullable=True),
        sa.Column("manual_balance_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("difference", sa.Numeric(24, 8), nullable=True),
        sa.Column(
            "tolerance",
            sa.Numeric(24, 8),
            nullable=False,
            server_default=sa.text("0.01"),
        ),
        # NEAR decomposed components (NULL for non-NEAR)
        sa.Column("onchain_liquid", sa.Numeric(24, 8), nullable=True),
        sa.Column("onchain_locked", sa.Numeric(24, 8), nullable=True),
        sa.Column("onchain_staked", sa.Numeric(24, 8), nullable=True),
        # Status
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="open",
        ),
        # Diagnosis
        sa.Column("diagnosis_category", sa.String(50), nullable=True),
        sa.Column("diagnosis_detail", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("diagnosis_confidence", sa.Numeric(4, 3), nullable=True),
        # Resolution
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        # Verification run metadata
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("rpc_error", sa.Text(), nullable=True),
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
        # Constraints
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'accepted', 'unverified')",
            name="ck_vr_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_vr_user_id"),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], name="fk_vr_wallet_id"),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["users.id"], name="fk_vr_resolved_by"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_verification_results"),
        sa.UniqueConstraint(
            "wallet_id", "token_symbol", name="uq_vr_wallet_token"
        ),
    )
    op.create_index("ix_vr_user_id", "verification_results", ["user_id"])
    op.create_index("ix_vr_wallet_id", "verification_results", ["wallet_id"])
    op.create_index("ix_vr_status", "verification_results", ["status"])
    op.create_index("ix_vr_verified_at", "verification_results", ["verified_at"])

    # ------------------------------------------------------------------
    # account_verification_status — per-wallet rollup for UI dashboard
    # ------------------------------------------------------------------
    op.create_table(
        "account_verification_status",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "open_issues",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        # Constraints
        sa.CheckConstraint(
            "status IN ('verified', 'flagged', 'unverified')",
            name="ck_avs_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_avs_user_id"),
        sa.ForeignKeyConstraint(
            ["wallet_id"], ["wallets.id"], name="fk_avs_wallet_id"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_account_verification_status"),
        sa.UniqueConstraint("wallet_id", name="uq_avs_wallet_id"),
    )
    op.create_index("ix_avs_user_id", "account_verification_status", ["user_id"])
    op.create_index("ix_avs_status", "account_verification_status", ["status"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("account_verification_status")
    op.drop_table("verification_results")
