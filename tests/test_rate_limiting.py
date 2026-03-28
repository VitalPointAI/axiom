"""Tests for API rate limiting via slowapi.

Covers QH-05: Rate limits on auth and job trigger endpoints.
"""


class TestRateLimiting:
    """Verify slowapi limiter is wired into the FastAPI application."""

    def test_limiter_registered_on_app(self):
        """The slowapi limiter must be registered on the FastAPI app state."""
        from api.main import app
        assert hasattr(app.state, "limiter"), "slowapi limiter not registered on app.state"

    def test_rate_limit_exception_handler_registered(self):
        """RateLimitExceeded exception handler must be registered."""
        from api.main import app
        from slowapi.errors import RateLimitExceeded
        handler = app.exception_handlers.get(RateLimitExceeded)
        assert handler is not None, "RateLimitExceeded exception handler not registered"

    def test_auth_router_has_limiter_import(self):
        """Auth router imports the shared limiter module."""
        import importlib
        auth_router_module = importlib.import_module("api.auth.router")
        assert hasattr(auth_router_module, "limiter"), "limiter not imported in auth router"

    def test_wallets_router_has_limiter_import(self):
        """Wallets router imports the shared limiter module."""
        import api.routers.wallets as wallets_module
        assert hasattr(wallets_module, "limiter"), "limiter not imported in wallets router"

    def test_transactions_router_has_limiter_import(self):
        """Transactions router imports the shared limiter module."""
        import api.routers.transactions as tx_module
        assert hasattr(tx_module, "limiter"), "limiter not imported in transactions router"

    def test_reports_router_has_limiter_import(self):
        """Reports router imports the shared limiter module."""
        import api.routers.reports as reports_module
        assert hasattr(reports_module, "limiter"), "limiter not imported in reports router"

    def test_limiter_key_func_is_remote_address(self):
        """Limiter must use get_remote_address as key function (rate by IP)."""
        from api.rate_limit import limiter
        from slowapi.util import get_remote_address
        assert limiter._key_func is get_remote_address, (
            "limiter key_func should be get_remote_address for IP-based rate limiting"
        )

    def test_allowed_update_fields_whitelist_exists(self):
        """ALLOWED_UPDATE_FIELDS whitelist must be defined in transactions router."""
        from api.routers.transactions import ALLOWED_UPDATE_FIELDS
        # Verify the expected fields are present
        assert "category" in ALLOWED_UPDATE_FIELDS
        assert "notes" in ALLOWED_UPDATE_FIELDS
        assert "needs_review" in ALLOWED_UPDATE_FIELDS
        # Verify no additional unexpected fields (security: whitelist should be minimal)
        assert len(ALLOWED_UPDATE_FIELDS) == 3, (
            f"ALLOWED_UPDATE_FIELDS should have exactly 3 fields, got {len(ALLOWED_UPDATE_FIELDS)}"
        )
