"""Add missing unique constraint uq_tc_tx_leg on transaction_classifications.

This constraint is required by the classifier's ON CONFLICT upsert logic.
It was referenced in code but never created by a migration.

Revision ID: 013
Revises: 012
"""

from alembic import op

revision = "013"
down_revision = "012"


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_tc_tx_leg'
            ) THEN
                ALTER TABLE transaction_classifications
                ADD CONSTRAINT uq_tc_tx_leg
                UNIQUE (user_id, transaction_id, leg_type);
            END IF;
        END $$
    """)


def downgrade():
    op.execute("""
        ALTER TABLE transaction_classifications
        DROP CONSTRAINT IF EXISTS uq_tc_tx_leg
    """)
