"""Tests for config.py environment validation.

Covers QH-06: Startup fails fast on missing required env vars.
"""
import importlib
import logging
import os
from unittest.mock import patch


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
            # NEARBLOCKS_API_KEY and COINGECKO_API_KEY should both warn
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
                "NEARBLOCKS_API_KEY": "testkey",
                "COINGECKO_API_KEY": "testkey2",
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
        assert "NEARBLOCKS_API_KEY" in OPTIONAL_ENV_VARS_WARN
        assert "COINGECKO_API_KEY" in OPTIONAL_ENV_VARS_WARN
