"""Resolve EVM token metadata via Alchemy getTokenMetadata.

Fetches symbol, name, decimals, and logo for all ERC-20 contract
addresses (0x...) found in transactions but missing from token_metadata.

Revision ID: 017
Revises: 016
"""

import logging
import os

from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"

logger = logging.getLogger(__name__)

ALCHEMY_API_KEY = os.environ.get("ALCHEMY_API_KEY")
ALCHEMY_URL = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}" if ALCHEMY_API_KEY else None


def upgrade():
    if not ALCHEMY_API_KEY:
        logger.warning("ALCHEMY_API_KEY not set, skipping EVM token resolution")
        return

    import requests

    conn = op.get_bind()

    # Find unresolved 0x addresses
    result = conn.execute(sa.text("""
        SELECT DISTINCT LOWER(t.token_id) AS tid
        FROM transactions t
        WHERE (t.token_id LIKE '0x%%' OR t.token_id LIKE '0X%%')
          AND LOWER(t.token_id) NOT IN (
              SELECT contract_id FROM token_metadata
              WHERE symbol IS NOT NULL AND fetch_failed = FALSE
          )
    """))
    unresolved = [row[0] for row in result]
    logger.info("Resolving %d EVM token addresses via Alchemy", len(unresolved))

    resolved = 0
    for contract_id in unresolved:
        try:
            resp = requests.post(
                ALCHEMY_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "alchemy_getTokenMetadata",
                    "params": [contract_id],
                },
                timeout=10,
            )
            data = resp.json()
            meta = data.get("result")
            if not meta or not meta.get("symbol"):
                # Mark as failed
                conn.execute(sa.text("""
                    INSERT INTO token_metadata (contract_id, chain, fetch_failed)
                    VALUES (:cid, 'ethereum', TRUE)
                    ON CONFLICT (contract_id) DO UPDATE SET fetch_failed = TRUE, fetched_at = NOW()
                """), {"cid": contract_id})
                continue

            conn.execute(sa.text("""
                INSERT INTO token_metadata (contract_id, chain, symbol, name, decimals, icon_url, fetch_failed)
                VALUES (:cid, 'ethereum', :sym, :name, :dec, :icon, FALSE)
                ON CONFLICT (contract_id) DO UPDATE SET
                    symbol = EXCLUDED.symbol,
                    name = EXCLUDED.name,
                    decimals = EXCLUDED.decimals,
                    icon_url = EXCLUDED.icon_url,
                    fetch_failed = FALSE,
                    fetched_at = NOW()
            """), {
                "cid": contract_id,
                "sym": meta["symbol"].upper(),
                "name": meta.get("name", ""),
                "dec": meta.get("decimals"),
                "icon": meta.get("logo", ""),
            })
            resolved += 1

        except Exception as e:
            logger.warning("Failed to resolve %s: %s", contract_id[:10], e)

    logger.info("Resolved %d/%d EVM tokens", resolved, len(unresolved))


def downgrade():
    pass
