# Axiom / NearTax Configuration

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

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

# ---------------------------------------------------------------------------
# Connection pool sizing
# ---------------------------------------------------------------------------
DB_POOL_MIN = int(os.environ.get("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.environ.get("DB_POOL_MAX", "10"))

# ---------------------------------------------------------------------------
# Job scheduling
# ---------------------------------------------------------------------------
JOB_POLL_INTERVAL = int(os.environ.get("JOB_POLL_INTERVAL", "5"))          # seconds
SYNC_INTERVAL_MINUTES = int(os.environ.get("SYNC_INTERVAL_MINUTES", "15"))  # minutes

# ---------------------------------------------------------------------------
# Offline / cached mode
# ---------------------------------------------------------------------------
# OFFLINE_MODE controls how the IndexerService handles network-dependent jobs.
#   "true"  — always skip network jobs (explicit offline mode).
#   "false" — never skip network jobs; failures will raise as usual.
#   "auto"  — perform a startup health check to NearBlocks; if unreachable,
#              activate offline mode automatically.
OFFLINE_MODE = os.environ.get("OFFLINE_MODE", "auto").lower()

# Job types that require external network access.
# These are skipped (re-queued) when offline mode is active.
NETWORK_JOB_TYPES = {
    "full_sync",
    "staking_sync",
    "lockup_sync",
    "evm_full_sync",
    "evm_incremental",
    "incremental_sync",
    "xrp_full_sync",
    "xrp_incremental",
    "akash_full_sync",
    "akash_incremental",
}

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

# ---------------------------------------------------------------------------
# Reconciliation tolerances (per-chain, in native token units)
# ---------------------------------------------------------------------------
# String values to convert cleanly to Decimal without float precision issues.
RECONCILIATION_TOLERANCES = {
    "near": "0.01",        # +/- 0.01 NEAR
    "ethereum": "0.0001",  # +/- 0.0001 ETH
    "polygon": "0.0001",   # +/- 0.0001 MATIC
    "cronos": "0.0001",    # +/- 0.0001 CRO
    "optimism": "0.0001",  # +/- 0.0001 ETH (Optimism)
}

# ---------------------------------------------------------------------------
# Environment validation
# ---------------------------------------------------------------------------

REQUIRED_ENV_VARS = ["DATABASE_URL"]
OPTIONAL_ENV_VARS_WARN = ["NEARBLOCKS_API_KEY", "COINGECKO_API_KEY"]

# Keys (or substrings) that should be redacted from log output.
_SENSITIVE_KEY_PATTERNS = {"DATABASE_URL", "API_KEY", "TOKEN", "SECRET", "PASSWORD"}


def sanitize_for_log(env_dict: dict) -> dict:
    """Return a copy of *env_dict* with sensitive values replaced by '***REDACTED***'.

    Matching is case-insensitive and substring-based so that variants like
    ``NEARBLOCKS_API_KEY``, ``SESSION_TOKEN``, and ``DB_PASSWORD`` are all
    caught without an exhaustive allowlist.

    Args:
        env_dict: Mapping of key → value (e.g. os.environ or a config dict).

    Returns:
        New dict with the same keys but sensitive values redacted.
        The original dict is never mutated.
    """
    redacted = {}
    for key, value in env_dict.items():
        upper_key = str(key).upper()
        if any(pattern in upper_key for pattern in _SENSITIVE_KEY_PATTERNS):
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


def validate_env() -> None:
    """Validate required environment variables at startup.

    Raises RuntimeError if any required variable is missing.
    Raises ValueError if pool sizing constraints are violated (MIN <= MAX, both > 0).
    Logs a warning for missing optional variables.

    Called by api/main.py lifespan before the DB pool is opened so the
    application fails fast rather than failing at first query.
    """
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f"Required environment variables not set: {', '.join(missing)}. "
            "Check .env file or container environment."
        )
    if DB_POOL_MIN <= 0:
        raise ValueError(
            f"DB_POOL_MIN must be > 0, got {DB_POOL_MIN}. "
            "Set DB_POOL_MIN env var to a positive integer."
        )
    if DB_POOL_MAX <= 0:
        raise ValueError(
            f"DB_POOL_MAX must be > 0, got {DB_POOL_MAX}. "
            "Set DB_POOL_MAX env var to a positive integer."
        )
    if DB_POOL_MIN > DB_POOL_MAX:
        raise ValueError(
            f"DB_POOL_MIN ({DB_POOL_MIN}) must be <= DB_POOL_MAX ({DB_POOL_MAX}). "
            "Adjust DB_POOL_MIN or DB_POOL_MAX env vars."
        )
    for var in OPTIONAL_ENV_VARS_WARN:
        if not os.environ.get(var):
            logger.warning("Optional env var %s not set — some features will be limited", var)
