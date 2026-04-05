"""Token metadata cache for dynamic FT symbol resolution.

Stores symbol, decimals, and name from on-chain ft_metadata calls.
Avoids repeated RPC calls for the same contract.

Revision ID: 015
Revises: 014
"""

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"


def upgrade():
    op.create_table(
        "token_metadata",
        sa.Column("contract_id", sa.Text(), primary_key=True),
        sa.Column("chain", sa.Text(), nullable=False, server_default="near"),
        sa.Column("symbol", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("decimals", sa.Integer(), nullable=True),
        sa.Column("icon_url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("fetch_failed", sa.Boolean(), server_default="false"),
    )
    op.create_index("idx_token_metadata_chain", "token_metadata", ["chain"])


def downgrade():
    op.drop_index("idx_token_metadata_chain")
    op.drop_table("token_metadata")
