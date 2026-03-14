"""Rate-limited NearBlocks API client with exponential backoff + jitter."""

import logging
import random
import time
import requests
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    NEARBLOCKS_BASE_URL,
    RATE_LIMIT_DELAY,
    MAX_RETRIES,
    INTER_WALLET_DELAY,
)

logger = logging.getLogger(__name__)


class NearBlocksClient:
    """NearBlocks API client with rate limiting and exponential backoff.

    Free tier hits 429 after ~6 rapid requests, so we:
    - Wait RATE_LIMIT_DELAY (1.0–3.0s) between ALL normal requests
    - Exponential backoff + jitter on 429, Timeout, or ConnectionError
    - Max 5 retries before raising RuntimeError (no silent data loss)
    """

    def __init__(self, base_url=None, delay=None, max_retries=None):
        self.base_url = base_url or NEARBLOCKS_BASE_URL
        self.delay = delay if delay is not None else RATE_LIMIT_DELAY
        self.max_retries = max_retries if max_retries is not None else MAX_RETRIES
        self.last_request_time = 0
        self.request_count = 0
        self.session = requests.Session()

    def _wait_for_rate_limit(self):
        """Ensure minimum delay between requests (normal inter-request pacing)."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay:
            wait_time = self.delay - elapsed
            time.sleep(wait_time)
        self.last_request_time = time.time()

    def _nearblocks_request(self, url, params=None):
        """Make NearBlocks API request with exponential backoff + jitter.

        Retry strategy (2^attempt + uniform jitter in [0, 1)):
          attempt 0 -> wait ~1s
          attempt 1 -> wait ~2s
          attempt 2 -> wait ~4s
          attempt 3 -> wait ~8s
          attempt 4 -> wait ~16s

        Handles:
          - 429 rate-limit responses
          - requests.exceptions.Timeout
          - requests.exceptions.ConnectionError

        After max_retries exhausted, raises RuntimeError (not silent failure).
        RATE_LIMIT_DELAY inter-request pacing is applied before each attempt.
        """
        for attempt in range(self.max_retries):
            self._wait_for_rate_limit()
            self.request_count += 1

            try:
                resp = self.session.get(url, params=params, timeout=30)

                if resp.status_code == 429:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "NearBlocks 429 rate limited, retry %d/%d in %.1fs: %s",
                        attempt + 1, self.max_retries, wait, url,
                    )
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                return resp.json()

            except requests.exceptions.Timeout:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "NearBlocks timeout, retry %d/%d in %.1fs: %s",
                    attempt + 1, self.max_retries, wait, url,
                )
                time.sleep(wait)

            except requests.exceptions.ConnectionError:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "NearBlocks connection error, retry %d/%d in %.1fs: %s",
                    attempt + 1, self.max_retries, wait, url,
                )
                time.sleep(wait)

        raise RuntimeError(
            f"NearBlocks API failed after {self.max_retries} retries: {url}"
        )

    def _request(self, endpoint, params=None):
        """Build full URL and delegate to _nearblocks_request."""
        url = f"{self.base_url}/{endpoint}"
        return self._nearblocks_request(url, params=params)

    def get_transaction_count(self, account_id):
        """Get total transaction count for account."""
        data = self._request(f"account/{account_id}/txns/count")
        return int(data["txns"][0]["count"])

    def fetch_transactions(self, account_id, cursor=None, per_page=25):
        """Fetch one page of transactions.

        Returns dict with:
        - txns: list of transaction objects
        - cursor: cursor for next page (None if last page)
        """
        endpoint = f"account/{account_id}/txns"
        params = {"per_page": per_page}
        if cursor:
            params["cursor"] = cursor
        return self._request(endpoint, params=params)

    def fetch_staking_deposits(self, account_id):
        """Get staking deposit summary from kitwallet endpoint.

        Returns list of validator deposits/withdrawals.
        """
        return self._request(f"kitwallet/staking-deposits/{account_id}")

    def get_stats(self):
        """Get client statistics."""
        return {
            "request_count": self.request_count,
            "delay": self.delay,
        }


if __name__ == "__main__":
    # Quick smoke test
    logging.basicConfig(level=logging.INFO)
    client = NearBlocksClient()

    print("Testing NearBlocks client...")

    count = client.get_transaction_count("vitalpointai.near")
    print(f"vitalpointai.near transaction count: {count}")

    result = client.fetch_transactions("vitalpointai.near", per_page=5)
    print(f"Fetched {len(result.get('txns', []))} transactions")
    if result.get("cursor"):
        print(f"Cursor: {result['cursor'][:20]}...")
    else:
        print("No cursor")

    deposits = client.fetch_staking_deposits("vitalpointai.near")
    print(f"Staking validators: {len(deposits)}")

    print(f"\nStats: {client.get_stats()}")
