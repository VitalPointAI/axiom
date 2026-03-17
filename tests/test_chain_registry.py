"""Unit tests for chain registry loader — mock pool/cursor, no live database."""

from unittest.mock import MagicMock

import pytest

from indexers.cost_tracker import load_chain_config


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()
    pool.getconn.return_value = conn
    conn.cursor.return_value = cursor
    return pool, conn, cursor


class TestLoadChainConfig:
    def test_returns_enabled_chains(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchall.return_value = [
            ("near", "NearStreamFetcher",
             ["near_stream_sync", "full_sync", "incremental_sync"],
             {"poll_interval": 0.6, "provider": "neardata_xyz"},
             None),
            ("ethereum", "EVMStreamFetcher",
             ["evm_full_sync", "evm_incremental"],
             {"ws_provider": "alchemy", "chain_id": 1},
             10.0),
        ]

        result = load_chain_config(pool)

        assert "near" in result
        assert "ethereum" in result
        assert result["near"]["fetcher_class"] == "NearStreamFetcher"
        assert result["ethereum"]["monthly_budget_usd"] == 10.0

    def test_query_filters_enabled_only(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchall.return_value = []

        load_chain_config(pool)

        sql = cursor.execute.call_args[0][0]
        assert "enabled" in sql.lower()
        assert "true" in sql.lower() or "= true" in sql.lower()

    def test_returns_empty_dict_when_no_chains(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchall.return_value = []

        result = load_chain_config(pool)

        assert result == {}

    def test_config_json_preserved(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchall.return_value = [
            ("polygon", "EVMStreamFetcher",
             ["evm_full_sync"],
             {"chain_id": 137, "ws_provider": "alchemy"},
             5.0),
        ]

        result = load_chain_config(pool)

        assert result["polygon"]["config_json"]["chain_id"] == 137

    def test_job_types_as_list(self, mock_pool):
        pool, conn, cursor = mock_pool
        cursor.fetchall.return_value = [
            ("xrp", "XRPFetcher",
             ["xrp_full_sync", "xrp_incremental"],
             {},
             None),
        ]

        result = load_chain_config(pool)

        assert isinstance(result["xrp"]["job_types"], list)
        assert "xrp_full_sync" in result["xrp"]["job_types"]
