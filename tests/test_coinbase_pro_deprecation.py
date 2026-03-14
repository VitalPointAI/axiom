"""Tests for coinbase_pro_indexer.py deprecation warning.

Covers RC-08: coinbase_pro_indexer.py emits DeprecationWarning on import.
"""
import importlib
import warnings


class TestCoinbaseProDeprecation:
    """Verify coinbase_pro_indexer emits DeprecationWarning on import."""

    def test_coinbase_pro_emits_deprecation_warning(self):
        """Importing coinbase_pro_indexer must emit a DeprecationWarning."""
        import indexers.coinbase_pro_indexer as coinbase_pro_indexer

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            importlib.reload(coinbase_pro_indexer)
            assert any(
                issubclass(warning.category, DeprecationWarning)
                for warning in w
            ), "Expected DeprecationWarning from coinbase_pro_indexer on reload"

    def test_coinbase_pro_deprecation_message_mentions_replacement(self):
        """DeprecationWarning message must mention the replacement module."""
        import indexers.coinbase_pro_indexer as coinbase_pro_indexer

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            importlib.reload(coinbase_pro_indexer)
            deprecation_warnings = [
                warning for warning in w
                if issubclass(warning.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1
            msg = str(deprecation_warnings[0].message)
            assert "coinbase" in msg.lower(), f"Expected 'coinbase' in warning message, got: {msg}"
