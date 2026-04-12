"""Add block-precise account->block pointer table.

Creates account_transactions table which maps each account to the exact
block heights where it appears as signer, receiver, or receipt destination.
Replaces segment-based indexing (account_block_index_v2) for wallet sync
lookups — instead of scanning 1000-block segment windows, wallet sync
fetches only the specific blocks where the account has activity.

Schema:
    account_int    INTEGER NOT NULL   -- FK (by value) into account_dictionary.id
    block_height   INTEGER NOT NULL
    PRIMARY KEY (account_int, block_height)

PK ordering puts account_int first so "all blocks for wallet X" queries
use an index-only range scan.

Storage design notes:
    - No tx_hash column: we only need to know which blocks have activity
      for an account. Wallet sync fetches the whole block and extracts
      all relevant transactions at read time (re-derives tx_hash from the
      block JSON), saving ~240 GB vs a (account, block, tx_hash) table.
    - 8 bytes per row × ~3B rows = ~24 GB raw data + ~30 GB btree index
      = ~55 GB total. Fits easily on the 500 GB pgdata volume.
    - INTEGER block_height is safe through ~2.1 billion blocks (~60+ years).

The account_block_index_v2 table is NOT dropped — it remains in the schema
for fallback/legacy use but is no longer written to by the v0.3 indexer.

Revision ID: 021
Revises: 020
"""

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"


def upgrade():
    op.create_table(
        "account_transactions",
        sa.Column("account_int", sa.Integer(), nullable=False),
        sa.Column("block_height", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "account_int", "block_height",
            name="account_transactions_pkey",
        ),
    )
    # PK already supports index-only scans for (account_int ordered by
    # block_height) queries, so no secondary index needed.


def downgrade():
    op.drop_table("account_transactions")
