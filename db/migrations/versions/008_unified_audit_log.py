"""Phase 11 migration: unified audit_log table.

Replaces the narrow classification_audit_log table with a general-purpose
audit_log table that covers all mutation points across the system:
  - Transaction classification changes
  - ACB corrections
  - Duplicate merges
  - Manual balance overrides
  - Report generation events
  - Invariant violations
  - Verification resolutions

Data from classification_audit_log is migrated into audit_log before the
old table is dropped. The column mapping preserves all auditable information
using JSONB for old_value/new_value fields.

Revision ID: 008
Revises: 007
Create Date: 2026-03-14 00:00:00 UTC
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # audit_log — unified audit trail for all data mutations
    # Append-only: never updated, only inserted.
    # ------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column(
            "old_value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "new_value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_al_user_id"),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )

    # Indexes use IF NOT EXISTS for idempotency
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_al_entity "
        "ON audit_log (entity_type, entity_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_al_user_id "
        "ON audit_log (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_al_created_at "
        "ON audit_log (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_al_action "
        "ON audit_log (action)"
    )

    # ------------------------------------------------------------------
    # Migrate existing classification_audit_log data
    # Column mapping:
    #   changed_by_user_id  -> user_id
    #   'transaction_classification' -> entity_type (literal)
    #   classification_id   -> entity_id
    #   change_reason       -> action
    #   old_category + old_confidence -> old_value (JSONB, NULL if both NULL)
    #   new_category + new_confidence -> new_value (JSONB)
    #   changed_by_type     -> actor_type
    #   notes               -> notes
    #   created_at          -> created_at
    # ------------------------------------------------------------------
    op.execute(
        """
        INSERT INTO audit_log
            (user_id, entity_type, entity_id, action,
             old_value, new_value, actor_type, notes, created_at)
        SELECT
            changed_by_user_id,
            'transaction_classification',
            classification_id,
            change_reason,
            CASE
                WHEN old_category IS NULL AND old_confidence IS NULL THEN NULL
                ELSE jsonb_build_object(
                    'category', old_category,
                    'confidence', old_confidence
                )
            END,
            jsonb_build_object(
                'category', new_category,
                'confidence', new_confidence
            ),
            changed_by_type,
            notes,
            created_at
        FROM classification_audit_log
        """
    )

    # ------------------------------------------------------------------
    # Drop old table now that data has been migrated
    # ------------------------------------------------------------------
    op.drop_table("classification_audit_log")


def downgrade() -> None:
    # Re-create classification_audit_log (same schema as migration 003)
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
        sa.ForeignKeyConstraint(
            ["rule_id"], ["classification_rules.id"], name="fk_cal_rule_id"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_classification_audit_log"),
    )
    op.create_index(
        "ix_cal_classification_id", "classification_audit_log", ["classification_id"]
    )
    op.create_index("ix_cal_created_at", "classification_audit_log", ["created_at"])

    # Drop audit_log (NOTE: migrated data is lost on downgrade)
    op.drop_table("audit_log")
