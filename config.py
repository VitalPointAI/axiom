# Axiom / NearTax Configuration

import os
from pathlib import Path

# Manual .env loading (no dotenv dependency)
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# No SQLite — PostgreSQL only.
# No hardcoded fallback: fail explicitly if DATABASE_URL is not set.
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL is None:
    print(
        "WARNING: DATABASE_URL is not set. "
        "Database operations will fail. "
        "Set DATABASE_URL=postgres://user:pass@host:5432/dbname"
    )

# ---------------------------------------------------------------------------
# Job scheduling
# ---------------------------------------------------------------------------
JOB_POLL_INTERVAL = int(os.environ.get("JOB_POLL_INTERVAL", "5"))          # seconds
SYNC_INTERVAL_MINUTES = int(os.environ.get("SYNC_INTERVAL_MINUTES", "15"))  # minutes

# ---------------------------------------------------------------------------
# NearBlocks API
# ---------------------------------------------------------------------------
NEARBLOCKS_BASE_URL = "https://api.nearblocks.io/v1"
NEARBLOCKS_API_KEY = os.environ.get("NEARBLOCKS_API_KEY")

# Rate limiting — Paid tier: ~190 calls/min. Use 1/sec to stay safe.
RATE_LIMIT_DELAY = 1.0 if NEARBLOCKS_API_KEY else 3.0
MAX_RETRIES = 5
BACKOFF_MULTIPLIER = 2.0
INTER_WALLET_DELAY = 2 if NEARBLOCKS_API_KEY else 10

# ---------------------------------------------------------------------------
# FastNear RPC (balance checks, no rate limit)
# ---------------------------------------------------------------------------
FASTNEAR_RPC = "https://free.rpc.fastnear.com"
FASTNEAR_ARCHIVAL_RPC = "https://archival-rpc.mainnet.fastnear.com"

# ---------------------------------------------------------------------------
# Price data APIs
# ---------------------------------------------------------------------------
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY")
CRYPTOCOMPARE_API_KEY = os.environ.get("CRYPTOCOMPARE_API_KEY", "")  # optional
