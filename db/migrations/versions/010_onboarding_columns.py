"""Add onboarding_completed_at and dismissed_banners columns to users table.

Revision ID: 010
"""

from alembic import op


revision = "010"
down_revision = "009"


def upgrade():
    op.execute("""
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS dismissed_banners JSONB DEFAULT '{}';
    """)


def downgrade():
    op.execute("""
        ALTER TABLE users
            DROP COLUMN IF EXISTS onboarding_completed_at,
            DROP COLUMN IF EXISTS dismissed_banners;
    """)
