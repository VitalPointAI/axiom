"""Add api_cost_log and chain_sync_config tables, api_cost_monthly view.

Revision ID: 011
"""

from alembic import op


revision = "011"
down_revision = "010"


def upgrade():
    # 1. api_cost_log — tracks individual API calls per chain/provider
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_cost_log (
            id BIGSERIAL PRIMARY KEY,
            logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            chain TEXT NOT NULL,
            provider TEXT NOT NULL,
            call_type TEXT NOT NULL,
            response_ms INT,
            estimated_cost_usd NUMERIC(12, 8) DEFAULT 0
        );
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_api_cost_log_chain_date
        ON api_cost_log (chain, logged_at DESC);
    """)

    # 2. chain_sync_config — per-chain fetcher configuration
    op.execute("""
        CREATE TABLE IF NOT EXISTS chain_sync_config (
            chain TEXT PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT true,
            fetcher_class TEXT NOT NULL,
            job_types TEXT[] NOT NULL,
            config_json JSONB NOT NULL DEFAULT '{}',
            monthly_budget_usd NUMERIC(8, 2),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # 3. api_cost_monthly view — aggregated cost data
    op.execute("""
        CREATE OR REPLACE VIEW api_cost_monthly AS
        SELECT
            chain,
            provider,
            call_type,
            date_trunc('month', logged_at) AS month,
            COUNT(*) AS call_count,
            SUM(estimated_cost_usd) AS total_cost_usd
        FROM api_cost_log
        GROUP BY 1, 2, 3, 4;
    """)

    # 4. Seed initial chain configurations
    op.execute("""
        INSERT INTO chain_sync_config (chain, fetcher_class, job_types, config_json)
        VALUES
            ('near', 'NearStreamFetcher',
             ARRAY['near_stream_sync','full_sync','incremental_sync','staking_sync','lockup_sync'],
             '{"poll_interval": 0.6, "provider": "neardata_xyz", "historical_provider": "nearblocks"}'::jsonb),
            ('ethereum', 'EVMStreamFetcher',
             ARRAY['evm_full_sync','evm_incremental'],
             '{"ws_provider": "alchemy", "historical_provider": "etherscan", "chain_id": 1}'::jsonb),
            ('polygon', 'EVMStreamFetcher',
             ARRAY['evm_full_sync','evm_incremental'],
             '{"ws_provider": "alchemy", "historical_provider": "etherscan", "chain_id": 137}'::jsonb),
            ('optimism', 'EVMStreamFetcher',
             ARRAY['evm_full_sync','evm_incremental'],
             '{"ws_provider": "alchemy", "historical_provider": "etherscan", "chain_id": 10}'::jsonb),
            ('cronos', 'EVMStreamFetcher',
             ARRAY['evm_full_sync','evm_incremental'],
             '{"ws_provider": "infura", "historical_provider": "etherscan", "chain_id": 25}'::jsonb),
            ('xrp', 'XRPFetcher',
             ARRAY['xrp_full_sync','xrp_incremental'],
             '{}'::jsonb),
            ('akash', 'AkashFetcher',
             ARRAY['akash_full_sync','akash_incremental'],
             '{}'::jsonb)
        ON CONFLICT (chain) DO NOTHING;
    """)


def downgrade():
    op.execute("DROP VIEW IF EXISTS api_cost_monthly;")
    op.execute("DROP TABLE IF EXISTS chain_sync_config;")
    op.execute("DROP TABLE IF EXISTS api_cost_log;")
