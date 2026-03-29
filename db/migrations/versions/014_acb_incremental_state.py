"""Add ACB incremental state tracking columns to users table.

Tracks high-water mark (last processed classification_id) and a flag to
force full replay when wallets are added or classifications change.

Revision ID: 014
Revises: 013
"""

from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"


def upgrade():
    op.add_column(
        "users",
        sa.Column("acb_high_water_mark", sa.Integer(), nullable=True,
                  comment="Max classification_id processed by last ACB run"),
    )
    op.add_column(
        "users",
        sa.Column("acb_full_replay_required", sa.Boolean(),
                  server_default="true", nullable=False,
                  comment="True when full ACB replay needed (new wallet, reclassification)"),
    )


def downgrade():
    op.drop_column("users", "acb_full_replay_required")
    op.drop_column("users", "acb_high_water_mark")
