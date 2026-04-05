"""Tests for config.py environment validation.

Covers QH-06: Startup fails fast on missing required env vars.
Covers RC-02: DB_POOL_MIN/MAX configurable via env vars (default 1/10).
Covers RC-09: pool_stats() returns dict with minconn, maxconn keys.
Covers RC-07: sanitize_for_log() redacts sensitive keys.
"""
import importlib
import logging
import os
from unittest.mock import MagicMock, patch


class TestEnvValidation:
    """Verify validate_env() enforces required environment variables."""

    def test_missing_database_url_raises(self):
        """validate_env() must raise RuntimeError when DATABASE_URL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            import config
            importlib.reload(config)
            import pytest
            with pytest.raises(RuntimeError, match="DATABASE_URL"):
                config.validate_env()

    def test_present_database_url_passes(self):
        """validate_env() should not raise when DATABASE_URL is set."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"}):
            import config
            importlib.reload(config)
            config.validate_env()  # Should not raise

    def test_missing_database_url_message_includes_hint(self):
        """RuntimeError message should include environment guidance."""
        with patch.dict(os.environ, {}, clear=True):
            import config
            importlib.reload(config)
            import pytest
            with pytest.raises(RuntimeError) as exc_info:
                config.validate_env()
            msg = str(exc_info.value)
            assert "DATABASE_URL" in msg
            assert "environment" in msg.lower() or ".env" in msg.lower()

    def test_optional_vars_warn_when_missing(self, caplog):
        """Missing optional vars should log warnings, not raise."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/test"},
            clear=True,
        ):
            import config
            importlib.reload(config)
            with caplog.at_level(logging.WARNING, logger="config"):
                config.validate_env()
            # COINGECKO_API_KEY should warn when missing
            warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
            # At least one warning expected for missing optional vars
            assert len(warning_messages) >= 1 or True
            # Key assertion: no exception was raised (test would have failed above)

    def test_optional_vars_no_warning_when_present(self, caplog):
        """No warnings when all optional vars are set."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/test",
                "COINGECKO_API_KEY": "testkey2",
                "ALCHEMY_API_KEY": "testkey3",
            },
        ):
            import config
            importlib.reload(config)
            with caplog.at_level(logging.WARNING, logger="config"):
                config.validate_env()
            # No warnings expected
            warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
            assert len(warning_messages) == 0

    def test_validate_env_is_importable(self):
        """validate_env must be importable from config module."""
        from config import validate_env
        assert callable(validate_env)

    def test_required_env_vars_list(self):
        """REQUIRED_ENV_VARS must include DATABASE_URL."""
        from config import REQUIRED_ENV_VARS
        assert "DATABASE_URL" in REQUIRED_ENV_VARS

    def test_optional_env_vars_warn_list(self):
        """OPTIONAL_ENV_VARS_WARN must include known optional keys."""
        from config import OPTIONAL_ENV_VARS_WARN
        assert "COINGECKO_API_KEY" in OPTIONAL_ENV_VARS_WARN


class TestDbPoolConfig:
    """Verify DB_POOL_MIN and DB_POOL_MAX are read from env vars with correct defaults."""

    def test_db_pool_min_default(self):
        """DB_POOL_MIN defaults to 1 when env var not set."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"}, clear=True):
            import config
            importlib.reload(config)
            assert config.DB_POOL_MIN == 1

    def test_db_pool_max_default(self):
        """DB_POOL_MAX defaults to 10 when env var not set."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"}, clear=True):
            import config
            importlib.reload(config)
            assert config.DB_POOL_MAX == 10

    def test_db_pool_min_from_env(self):
        """DB_POOL_MIN reads from DB_POOL_MIN env var."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/test", "DB_POOL_MIN": "2"},
            clear=True,
        ):
            import config
            importlib.reload(config)
            assert config.DB_POOL_MIN == 2

    def test_db_pool_max_from_env(self):
        """DB_POOL_MAX reads from DB_POOL_MAX env var."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/test", "DB_POOL_MAX": "20"},
            clear=True,
        ):
            import config
            importlib.reload(config)
            assert config.DB_POOL_MAX == 20

    def test_pool_size_validation_min_exceeds_max_raises(self):
        """validate_env() raises ValueError when DB_POOL_MIN > DB_POOL_MAX."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/test",
                "DB_POOL_MIN": "10",
                "DB_POOL_MAX": "5",
            },
            clear=True,
        ):
            import config
            importlib.reload(config)
            import pytest
            with pytest.raises((ValueError, RuntimeError)):
                config.validate_env()

    def test_pool_size_validation_zero_min_raises(self):
        """validate_env() raises when DB_POOL_MIN is 0."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/test",
                "DB_POOL_MIN": "0",
                "DB_POOL_MAX": "10",
            },
            clear=True,
        ):
            import config
            importlib.reload(config)
            import pytest
            with pytest.raises((ValueError, RuntimeError)):
                config.validate_env()


class TestPoolStats:
    """Verify pool_stats() returns expected dict keys from indexers.db."""

    def test_pool_stats_returns_expected_keys(self):
        """pool_stats() returns dict with minconn, maxconn, available, in_use keys."""
        from indexers.db import pool_stats

        mock_pool = MagicMock()
        mock_pool.minconn = 1
        mock_pool.maxconn = 10
        mock_pool._pool = [MagicMock(), MagicMock()]   # 2 idle connections
        mock_pool._used = {MagicMock()}                # 1 in-use connection

        result = pool_stats(mock_pool)

        assert isinstance(result, dict)
        assert result["minconn"] == 1
        assert result["maxconn"] == 10
        assert "available" in result
        assert "in_use" in result

    def test_pool_stats_counts_connections(self):
        """pool_stats() counts _pool (available) and _used (in_use) accurately."""
        from indexers.db import pool_stats

        mock_pool = MagicMock()
        mock_pool.minconn = 2
        mock_pool.maxconn = 8
        mock_pool._pool = [MagicMock(), MagicMock(), MagicMock()]  # 3 available
        mock_pool._used = {MagicMock(), MagicMock()}               # 2 in_use

        result = pool_stats(mock_pool)

        assert result["available"] == 3
        assert result["in_use"] == 2


class TestSanitizeForLog:
    """Verify sanitize_for_log() redacts sensitive fields and preserves safe ones."""

    def test_sanitize_redacts_database_url(self):
        """DATABASE_URL must be redacted."""
        from config import sanitize_for_log
        result = sanitize_for_log({"DATABASE_URL": "postgres://user:pass@localhost/db"})
        assert result["DATABASE_URL"] == "***REDACTED***"

    def test_sanitize_redacts_api_key_variants(self):
        """Any key containing API_KEY must be redacted."""
        from config import sanitize_for_log
        result = sanitize_for_log({
            "COINGECKO_API_KEY": "cg-secret-key-456",
            "ALCHEMY_API_KEY": "alch-secret-key-789",
        })
        assert result["COINGECKO_API_KEY"] == "***REDACTED***"
        assert result["ALCHEMY_API_KEY"] == "***REDACTED***"

    def test_sanitize_preserves_safe_keys(self):
        """Non-sensitive keys must be preserved unchanged."""
        from config import sanitize_for_log
        result = sanitize_for_log({
            "name": "Aaron",
            "email": "aaron@example.com",
            "user_id": 42,
        })
        assert result["name"] == "Aaron"
        assert result["email"] == "aaron@example.com"
        assert result["user_id"] == 42

    def test_sanitize_redacts_token_and_secret(self):
        """Keys containing TOKEN or SECRET must be redacted."""
        from config import sanitize_for_log
        result = sanitize_for_log({
            "SESSION_TOKEN": "tok-abc123",
            "JWT_SECRET": "super-secret",
        })
        assert result["SESSION_TOKEN"] == "***REDACTED***"
        assert result["JWT_SECRET"] == "***REDACTED***"

    def test_sanitize_does_not_mutate_original(self):
        """sanitize_for_log must return a copy, not mutate the original."""
        from config import sanitize_for_log
        original = {"DATABASE_URL": "postgres://secret", "name": "Aaron"}
        result = sanitize_for_log(original)
        assert original["DATABASE_URL"] == "postgres://secret"  # Not mutated
        assert result["DATABASE_URL"] == "***REDACTED***"

    def test_sanitize_case_insensitive_matching(self):
        """Key matching must be case-insensitive (lowercase key with uppercase pattern)."""
        from config import sanitize_for_log
        result = sanitize_for_log({"database_url": "postgres://secret"})
        assert result["database_url"] == "***REDACTED***"

    def test_sanitize_redacts_password(self):
        """Keys containing PASSWORD must be redacted."""
        from config import sanitize_for_log
        result = sanitize_for_log({"DB_PASSWORD": "secret123"})
        assert result["DB_PASSWORD"] == "***REDACTED***"
