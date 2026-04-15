"""Integration test conftest.

Provides fixtures shared by tests/integration/*.  Inherits all fixtures from
the parent tests/conftest.py via pytest's conftest cascade.

Integration tests require a real PostgreSQL database at alembic revision 023.
They are gated on RUN_MIGRATION_TESTS=1 to avoid running in CI without a DB.
"""

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require a running PostgreSQL database (deselect with -m 'not integration')",
    )
