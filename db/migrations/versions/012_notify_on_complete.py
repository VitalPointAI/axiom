"""Add notify_on_complete column to users table.

Revision ID: 012
Revises: 011
"""

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"


def upgrade():
    op.add_column(
        "users",
        sa.Column("notify_on_complete", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade():
    op.drop_column("users", "notify_on_complete")
