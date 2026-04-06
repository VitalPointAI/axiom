"""Healthcheck for the account indexer sidecar.

Exits 0 if the indexer has updated within the last 5 minutes.
Exits 1 if stale or unreachable. Used by Docker HEALTHCHECK.

Usage:
    python -m indexers.account_indexer_health
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

MAX_STALE_SECONDS = 300  # 5 minutes


def check():
    from indexers.db import get_pool, close_pool
    from datetime import datetime, timezone

    pool = get_pool(min_conn=1, max_conn=1)
    try:
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT updated_at FROM account_indexer_state WHERE id = 1")
            row = cur.fetchone()
            cur.close()

            if not row or not row[0]:
                print("UNHEALTHY: no indexer state found")
                return 1

            updated_at = row[0]
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)

            age = (datetime.now(timezone.utc) - updated_at).total_seconds()
            if age > MAX_STALE_SECONDS:
                print(f"UNHEALTHY: last update {int(age)}s ago (max {MAX_STALE_SECONDS}s)")
                return 1

            print(f"HEALTHY: last update {int(age)}s ago")
            return 0
        finally:
            pool.putconn(conn)
    except Exception as exc:
        print(f"UNHEALTHY: {exc}")
        return 1
    finally:
        close_pool()


if __name__ == "__main__":
    sys.exit(check())
