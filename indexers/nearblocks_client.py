"""Rate-limited NearBlocks API client with exponential backoff."""

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
    BACKOFF_MULTIPLIER,
    INTER_WALLET_DELAY
)

# Initial backoff after hitting rate limit (before multiplier kicks in)
INITIAL_RATE_LIMIT_WAIT = 30  # seconds


class NearBlocksClient:
    """
    NearBlocks API client with rate limiting.
    
    Free tier hits 429 after ~6 rapid requests, so we:
    - Wait RATE_LIMIT_DELAY (1.5s) between ALL requests
    - Exponential backoff on 429 errors
    - Max retries before giving up
    """
    
    def __init__(self, base_url=None, delay=None):
        self.base_url = base_url or NEARBLOCKS_BASE_URL
        self.delay = delay or RATE_LIMIT_DELAY
        self.last_request_time = 0
        self.request_count = 0
    
    def _wait_for_rate_limit(self):
        """Ensure minimum delay between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay:
            wait_time = self.delay - elapsed
            time.sleep(wait_time)
        self.last_request_time = time.time()
    
    def _request(self, endpoint, retries=0):
        """Make request with rate limiting and exponential backoff."""
        self._wait_for_rate_limit()
        self.request_count += 1
        
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = requests.get(url, timeout=30)
            
            if response.status_code == 429:
                if retries < MAX_RETRIES:
                    # Start with a longer initial wait, then exponential backoff
                    if retries == 0:
                        wait_time = INITIAL_RATE_LIMIT_WAIT
                    else:
                        wait_time = INITIAL_RATE_LIMIT_WAIT + (self.delay * (BACKOFF_MULTIPLIER ** retries))
                    print(f"  Rate limited, waiting {wait_time:.1f}s (retry {retries+1}/{MAX_RETRIES})")
                    time.sleep(wait_time)
                    return self._request(endpoint, retries + 1)
                raise Exception(f"Rate limit exceeded after {MAX_RETRIES} retries")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout:
            if retries < MAX_RETRIES:
                print(f"  Timeout, retrying ({retries+1}/{MAX_RETRIES})")
                time.sleep(self.delay)
                return self._request(endpoint, retries + 1)
            raise
        except requests.exceptions.RequestException as e:
            if retries < MAX_RETRIES:
                print(f"  Request error: {e}, retrying ({retries+1}/{MAX_RETRIES})")
                time.sleep(self.delay * (BACKOFF_MULTIPLIER ** retries))
                return self._request(endpoint, retries + 1)
            raise
    
    def get_transaction_count(self, account_id):
        """Get total transaction count for account."""
        data = self._request(f"account/{account_id}/txns/count")
        return int(data['txns'][0]['count'])
    
    def fetch_transactions(self, account_id, cursor=None, per_page=25):
        """
        Fetch one page of transactions.
        
        Returns dict with:
        - txns: list of transaction objects
        - cursor: cursor for next page (None if last page)
        """
        endpoint = f"account/{account_id}/txns?per_page={per_page}"
        if cursor:
            endpoint += f"&cursor={cursor}"
        return self._request(endpoint)
    
    def fetch_staking_deposits(self, account_id):
        """
        Get staking deposit summary from kitwallet endpoint.
        
        Returns list of validator deposits/withdrawals.
        """
        return self._request(f"kitwallet/staking-deposits/{account_id}")
    
    def get_stats(self):
        """Get client statistics."""
        return {
            "request_count": self.request_count,
            "delay": self.delay
        }


if __name__ == "__main__":
    # Test the client
    client = NearBlocksClient()
    
    print("Testing NearBlocks client...")
    
    # Test transaction count
    count = client.get_transaction_count("vitalpointai.near")
    print(f"vitalpointai.near transaction count: {count}")
    
    # Test fetching transactions
    result = client.fetch_transactions("vitalpointai.near", per_page=5)
    print(f"Fetched {len(result.get('txns', []))} transactions")
    print(f"Cursor: {result.get('cursor', 'none')[:20]}..." if result.get('cursor') else "No cursor")
    
    # Test staking deposits
    deposits = client.fetch_staking_deposits("vitalpointai.near")
    print(f"Staking validators: {len(deposits)}")
    
    print(f"\nStats: {client.get_stats()}")
