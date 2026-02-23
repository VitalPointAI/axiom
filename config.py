# NearTax Configuration

import os

# Database
DATABASE_PATH = os.environ.get("NEARTAX_DB", "neartax.db")

# NearBlocks API
NEARBLOCKS_BASE_URL = "https://api.nearblocks.io/v1"

# Rate limiting - NearBlocks free tier limits after ~6 rapid requests
RATE_LIMIT_DELAY = 1.5  # seconds between requests
MAX_RETRIES = 5
BACKOFF_MULTIPLIER = 2.0

# FastNear RPC (for balance checks, no rate limit)
FASTNEAR_RPC = "https://free.rpc.fastnear.com"
FASTNEAR_ARCHIVAL_RPC = "https://archival-rpc.mainnet.fastnear.com"
