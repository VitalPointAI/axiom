"""Phase 3 classification schema.

Creates tables for transaction classification, rule management,
spam detection, and audit logging:
  - transaction_classifications: per-transaction tax category assignments
  - classification_rules: rule-based classifier definitions (JSONB pattern matching)
  - spam_rules: user/system spam detection rules
  - classification_audit_log: immutable audit trail for classification changes

Supports multi-leg decomposition (parent/sell_leg/buy_leg/fee_leg),
staking reward linkage (CLASS-03), lockup vest linkage (CLASS-04),
and specialist confirmation workflow.

Revision ID: 003
Revises: 002b
Create Date: 2026-03-12 00:00:00 UTC
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "003"
down_revision: Union[str, None] = "002b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # classification_rules
    # Must be created before transaction_classifications (FK reference)
    # ------------------------------------------------------------------
    op.create_table(
        "classification_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("chain", sa.String(20), nullable=False),
        sa.Column("pattern", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("specialist_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sample_tx_count", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], name="fk_cr_confirmed_by"),
        sa.PrimaryKeyConstraint("id", name="pk_classification_rules"),
        sa.UniqueConstraint("name", name="uq_cr_name"),
    )
    op.create_index("ix_cr_chain", "classification_rules", ["chain"])
    op.create_index("ix_cr_is_active", "classification_rules", ["is_active"])
    op.create_index("ix_cr_priority", "classification_rules", ["priority"])

    # ------------------------------------------------------------------
    # transaction_classifications
    # ------------------------------------------------------------------
    op.create_table(
        "transaction_classifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("exchange_transaction_id", sa.Integer(), nullable=True),
        sa.Column("parent_classification_id", sa.Integer(), nullable=True),
        sa.Column("leg_type", sa.String(20), nullable=False, server_default="parent"),
        sa.Column("leg_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("classification_source", sa.String(20), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=True),
        sa.Column("staking_event_id", sa.Integer(), nullable=True),
        sa.Column("lockup_event_id", sa.Integer(), nullable=True),
        sa.Column("fmv_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("fmv_cad", sa.Numeric(18, 8), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("specialist_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_tc_user_id"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], name="fk_tc_transaction_id"),
        sa.ForeignKeyConstraint(
            ["exchange_transaction_id"],
            ["exchange_transactions.id"],
            name="fk_tc_exchange_transaction_id",
        ),
        sa.ForeignKeyConstraint(
            ["parent_classification_id"],
            ["transaction_classifications.id"],
            name="fk_tc_parent_classification_id",
        ),
        sa.ForeignKeyConstraint(["rule_id"], ["classification_rules.id"], name="fk_tc_rule_id"),
        sa.ForeignKeyConstraint(
            ["staking_event_id"], ["staking_events.id"], name="fk_tc_staking_event_id"
        ),
        sa.ForeignKeyConstraint(
            ["lockup_event_id"], ["lockup_events.id"], name="fk_tc_lockup_event_id"
        ),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], name="fk_tc_confirmed_by"),
        sa.PrimaryKeyConstraint("id", name="pk_transaction_classifications"),
    )
    op.create_index("ix_tc_user_id", "transaction_classifications", ["user_id"])
    op.create_index("ix_tc_transaction_id", "transaction_classifications", ["transaction_id"])
    op.create_index(
        "ix_tc_exchange_transaction_id",
        "transaction_classifications",
        ["exchange_transaction_id"],
    )
    op.create_index(
        "ix_tc_parent_id", "transaction_classifications", ["parent_classification_id"]
    )
    op.create_index("ix_tc_category", "transaction_classifications", ["category"])
    op.create_index("ix_tc_needs_review", "transaction_classifications", ["needs_review"])

    # Partial unique indexes (WHERE clause requires op.execute — op.create_unique_constraint
    # does not support partial indexes)
    op.execute(
        """
        CREATE UNIQUE INDEX uq_tc_user_tx_leg
        ON transaction_classifications (user_id, transaction_id, leg_type)
        WHERE transaction_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_tc_user_etx_leg
        ON transaction_classifications (user_id, exchange_transaction_id, leg_type)
        WHERE exchange_transaction_id IS NOT NULL
        """
    )

    # ------------------------------------------------------------------
    # spam_rules
    # ------------------------------------------------------------------
    op.create_table(
        "spam_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sr_user_id"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_sr_created_by"),
        sa.PrimaryKeyConstraint("id", name="pk_spam_rules"),
    )
    op.create_index("ix_sr_user_id", "spam_rules", ["user_id"])
    op.create_index("ix_sr_rule_type", "spam_rules", ["rule_type"])

    # ------------------------------------------------------------------
    # classification_audit_log
    # Immutable — never updated, only inserted
    # ------------------------------------------------------------------
    op.create_table(
        "classification_audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("classification_id", sa.Integer(), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("changed_by_type", sa.String(20), nullable=False),
        sa.Column("old_category", sa.String(50), nullable=True),
        sa.Column("new_category", sa.String(50), nullable=False),
        sa.Column("old_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("new_confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("change_reason", sa.String(50), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["classification_id"],
            ["transaction_classifications.id"],
            name="fk_cal_classification_id",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"], ["users.id"], name="fk_cal_changed_by_user_id"
        ),
        sa.ForeignKeyConstraint(["rule_id"], ["classification_rules.id"], name="fk_cal_rule_id"),
        sa.PrimaryKeyConstraint("id", name="pk_classification_audit_log"),
    )
    op.create_index(
        "ix_cal_classification_id", "classification_audit_log", ["classification_id"]
    )
    op.create_index("ix_cal_created_at", "classification_audit_log", ["created_at"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("classification_audit_log")
    op.drop_table("spam_rules")
    op.drop_table("transaction_classifications")
    op.drop_table("classification_rules")
