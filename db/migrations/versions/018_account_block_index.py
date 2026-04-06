"""Create account_block_index table for fast wallet lookups.

Maps NEAR account IDs to the block heights where they appear as
signer, receiver, or predecessor. Enables instant wallet history
queries instead of scanning millions of blocks via neardata.xyz.

Built by the account_indexer sidecar service.

Revision ID: 018
Revises: 017
"""

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"


def upgrade():
    op.create_table(
        "account_block_index",
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("block_height", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "block_height"),
    )
    # Index for fast lookups: "give me all blocks for this account"
    op.create_index(
        "ix_abi_account_block",
        "account_block_index",
        ["account_id", "block_height"],
    )

    # Metadata table to track indexer progress
    op.create_table(
        "account_indexer_state",
        sa.Column("id", sa.Integer(), primary_key=True, default=1),
        sa.Column("last_processed_block", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "INSERT INTO account_indexer_state (id, last_processed_block) VALUES (1, 0)"
    )


def downgrade():
    op.drop_table("account_indexer_state")
    op.drop_index("ix_abi_account_block", "account_block_index")
    op.drop_table("account_block_index")
