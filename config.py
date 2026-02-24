# NearTax Configuration

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

# Database
DATABASE_PATH = os.environ.get("NEARTAX_DB", "neartax.db")

# NearBlocks API
NEARBLOCKS_BASE_URL = "https://api.nearblocks.io/v1"
NEARBLOCKS_API_KEY = os.environ.get("NEARBLOCKS_API_KEY")

# Rate limiting - Paid tier: 190 calls/min = 3.2/sec, use 1/sec to be safe
RATE_LIMIT_DELAY = 1.0 if NEARBLOCKS_API_KEY else 3.0
MAX_RETRIES = 5
BACKOFF_MULTIPLIER = 2.0
INTER_WALLET_DELAY = 2 if NEARBLOCKS_API_KEY else 10

# FastNear RPC (for balance checks, no rate limit)
FASTNEAR_RPC = "https://free.rpc.fastnear.com"
FASTNEAR_ARCHIVAL_RPC = "https://archival-rpc.mainnet.fastnear.com"
