"""Phase 10 migration: price_cache composite index for efficient range queries.

Adds a composite index on price_cache(coin_id, date DESC) to accelerate
ordered range lookups like "all NEAR prices in 2024" which are common in
ACB calculations and report generation.

Also ensures the price_cache_minute table has its coin/timestamp index
(ix_pcm_coin_ts) with IF NOT EXISTS safety so this migration is idempotent
if index was created manually or by a prior hotfix.

Changes:
  - CREATE INDEX IF NOT EXISTS ix_price_cache_coin_date_desc ON price_cache (coin_id, date DESC)
  - CREATE INDEX IF NOT EXISTS ix_pcm_coin_ts ON price_cache_minute (coin_id, unix_ts)

Revision ID: 007
Revises: 006
Create Date: 2026-03-14 00:00:00 UTC
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite index for efficient ordered range queries on price_cache.
    # date DESC ordering matches the typical query pattern:
    #   WHERE coin_id = %s AND date BETWEEN %s AND %s ORDER BY date DESC
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_price_cache_coin_date_desc "
        "ON price_cache (coin_id, date DESC)"
    )

    # Safety net for price_cache_minute index — may already exist from plan 04-01.
    # IF NOT EXISTS ensures the migration is idempotent.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pcm_coin_ts "
        "ON price_cache_minute (coin_id, unix_ts)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_price_cache_coin_date_desc")
    # Do NOT drop ix_pcm_coin_ts — it may have pre-existed this migration.
