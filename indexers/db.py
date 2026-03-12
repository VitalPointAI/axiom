"""
Shared PostgreSQL connection helpers for all Axiom indexers.

Usage examples:

    # Single connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
    finally:
        conn.close()

    # Connection pool (long-lived processes)
    pool = get_pool()
    conn = pool.getconn()
    pool.putconn(conn)

    # Context manager (recommended)
    with db_cursor() as cur:
        cur.execute("INSERT INTO ...")
"""

import sys
from contextlib import contextmanager
from typing import Generator, Optional

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2.extensions import connection as PgConnection
from psycopg2.extensions import cursor as PgCursor

# Import DATABASE_URL from project config — no hardcoded fallbacks.
# config.py already prints a warning if DATABASE_URL is None.
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE_URL

# ---------------------------------------------------------------------------
# Module-level pool singleton
# ---------------------------------------------------------------------------
_pool: Optional[pg_pool.SimpleConnectionPool] = None


def _require_database_url() -> str:
    """Return DATABASE_URL or raise a clear error."""
    if not DATABASE_URL:
        raise EnvironmentError(
            "DATABASE_URL is not set. "
            "Export DATABASE_URL=postgres://user:pass@host:5432/dbname "
            "before running this script."
        )
    return DATABASE_URL


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_connection() -> PgConnection:
    """Open and return a new psycopg2 connection.

    Caller is responsible for closing it.
    Raises EnvironmentError if DATABASE_URL is not configured.
    """
    url = _require_database_url()
    return psycopg2.connect(url)


def get_pool(min_conn: int = 1, max_conn: int = 5) -> pg_pool.SimpleConnectionPool:
    """Return the module-level SimpleConnectionPool, creating it if needed.

    Suitable for long-lived indexer processes that need connection reuse.
    Thread-safe for reading; initialize before spawning threads.
    """
    global _pool
    if _pool is None:
        url = _require_database_url()
        _pool = pg_pool.SimpleConnectionPool(min_conn, max_conn, url)
    return _pool


def close_pool() -> None:
    """Close all connections in the pool and reset the singleton.

    Call this on process shutdown or in test teardown.
    """
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def db_cursor(autocommit: bool = False) -> Generator[PgCursor, None, None]:
    """Context manager that yields a psycopg2 cursor.

    Commits on clean exit, rolls back on exception.
    Creates a new connection each time (suitable for short-lived scripts).

    Args:
        autocommit: If True, set autocommit on the connection (no transaction).

    Yields:
        psycopg2 cursor

    Example:
        with db_cursor() as cur:
            cur.execute("INSERT INTO wallets (user_id, account_id) VALUES (%s, %s)", (1, "a.near"))
    """
    conn = get_connection()
    try:
        if autocommit:
            conn.autocommit = True
        cur = conn.cursor()
        try:
            yield cur
            if not autocommit:
                conn.commit()
        except Exception:
            if not autocommit:
                conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        conn.close()
