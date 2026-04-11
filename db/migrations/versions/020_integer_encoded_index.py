"""Add dictionary-encoded integer index for account_block_index.

Creates account_dictionary (string->int mapping) and account_block_index_v2
(integer-encoded account + segment pairs). Does NOT drop the original
account_block_index or account_indexer_state tables -- both old and new
tables coexist during transition.

The account_dictionary table maps NEAR account ID strings (e.g.
"vitalpointai.near") to compact INTEGER IDs, reducing per-row storage
from ~70 bytes (TEXT + BIGINT) to ~36 bytes (INTEGER + INTEGER).

The account_block_index_v2 table stores (account_int, segment_start) pairs
where segment_start is the 1,000-block segment boundary (block_height //
1000 * 1000), enabling efficient range-based lookups.

INTEGER safety margins:
  - block heights: ~186M current vs 2,147,483,647 max (~62 years headroom)
  - account count: ~15M current vs 2,147,483,647 max (~0.7% used)

Revision ID: 020
Revises: 019
"""

from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"


def upgrade():
    # Dictionary: maps account_id strings to compact integers.
    # The UNIQUE constraint automatically creates a B-tree index used for
    # string -> int lookups. The explicit ix_account_dictionary_account_id
    # index is created separately for named-index drop support in downgrade.
    op.create_table(
        "account_dictionary",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Text(), nullable=False, unique=True),
    )
    op.create_index(
        "ix_account_dictionary_account_id",
        "account_dictionary",
        ["account_id"],
        unique=True,
    )

    # New integer-encoded index table.
    # account_int: foreign key (by value) into account_dictionary.id
    # segment_start: 1,000-block segment boundary (block_height // 1000 * 1000)
    # Composite primary key prevents duplicate (account, segment) entries.
    op.create_table(
        "account_block_index_v2",
        sa.Column("account_int", sa.Integer(), nullable=False),
        sa.Column("segment_start", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("account_int", "segment_start"),
    )
    # Lookup index: "give me all segments for this account"
    op.create_index(
        "ix_abiv2_account_segment",
        "account_block_index_v2",
        ["account_int", "segment_start"],
    )


def downgrade():
    op.drop_index("ix_abiv2_account_segment", table_name="account_block_index_v2")
    op.drop_table("account_block_index_v2")
    op.drop_index("ix_account_dictionary_account_id", table_name="account_dictionary")
    op.drop_table("account_dictionary")
