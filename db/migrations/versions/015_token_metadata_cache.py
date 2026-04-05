"""015 — Token metadata cache for dynamic FT symbol resolution.

Stores symbol, decimals, and name from on-chain ft_metadata calls.
Avoids repeated RPC calls for the same contract.
"""

MIGRATION_ID = "015"
DESCRIPTION = "Token metadata cache table"
DEPENDS_ON = "014"


def upgrade(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS token_metadata (
            contract_id  TEXT PRIMARY KEY,
            chain        TEXT NOT NULL DEFAULT 'near',
            symbol       TEXT,
            name         TEXT,
            decimals     INTEGER,
            icon_url     TEXT,
            fetched_at   TIMESTAMP DEFAULT NOW(),
            fetch_failed BOOLEAN DEFAULT FALSE
        );

        CREATE INDEX IF NOT EXISTS idx_token_metadata_chain
            ON token_metadata (chain);
    """)
    conn.commit()
    cur.close()


def downgrade(conn):
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS token_metadata;")
    conn.commit()
    cur.close()
