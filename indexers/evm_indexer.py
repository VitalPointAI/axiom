#!/usr/bin/env python3
"""
EVM chain indexer using Etherscan/Polygonscan APIs.

NOTE: Free tier without API keys has severe limitations.
For production use, get free API keys from:
- Etherscan: https://etherscan.io/apis
- Polygonscan: https://polygonscan.com/apis
- Optimism: https://optimistic.etherscan.io/apis

Set in config.py or environment:
ETHERSCAN_API_KEY, POLYGONSCAN_API_KEY, OPTIMISM_API_KEY
"""

import time
import requests
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection

# API endpoints - V2 format requires different approach
# Free tier without API key is very limited, so we use alternative endpoints
CHAIN_APIS = {
    "ethereum": "https://api.etherscan.io/v2/api",
    "polygon": "https://api.polygonscan.com/api",
    "optimism": "https://api-optimistic.etherscan.io/api"
}

# For free tier, we can also try Blockscout (more permissive)
BLOCKSCOUT_APIS = {
    "ethereum": None,  # No free blockscout for mainnet
    "polygon": "https://polygon.blockscout.com/api",
    "optimism": "https://optimism.blockscout.com/api"
}

# Rate limit: 5 calls/second for free tier
RATE_LIMIT_DELAY = 0.25


class EVMIndexer:
    """Index EVM transactions from block explorers."""
    
    def __init__(self, chain="ethereum", api_key=None):
        self.chain = chain
        self.base_url = CHAIN_APIS.get(chain)
        self.api_key = api_key or ""  # Free tier works without key
        self.last_request = 0
    
    def _wait_rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self.last_request = time.time()
    
    def _request(self, params):
        self._wait_rate_limit()
        if self.api_key:
            params["apikey"] = self.api_key
        
        response = requests.get(self.base_url, params=params, timeout=30)
        data = response.json()
        
        if data.get("status") == "0" and "No transactions found" not in data.get("message", ""):
            print(f"  API Error: {data.get('message', 'Unknown error')}")
        
        return data.get("result", [])
    
    def get_normal_transactions(self, address, start_block=0):
        """Get normal (external) transactions."""
        return self._request({
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": start_block,
            "endblock": 99999999,
            "sort": "asc"
        })
    
    def get_internal_transactions(self, address, start_block=0):
        """Get internal transactions."""
        return self._request({
            "module": "account",
            "action": "txlistinternal",
            "address": address,
            "startblock": start_block,
            "endblock": 99999999,
            "sort": "asc"
        })
    
    def get_erc20_transfers(self, address, start_block=0):
        """Get ERC20 token transfers."""
        return self._request({
            "module": "account",
            "action": "tokentx",
            "address": address,
            "startblock": start_block,
            "endblock": 99999999,
            "sort": "asc"
        })
    
    def get_balance(self, address):
        """Get current ETH balance."""
        result = self._request({
            "module": "account",
            "action": "balance",
            "address": address,
            "tag": "latest"
        })
        if result and result != "0":
            return int(result) / 1e18
        return 0


def get_or_create_evm_wallet(address, chain):
    """Get or create EVM wallet record."""
    conn = get_connection()
    address = address.lower()
    
    row = conn.execute(
        "SELECT id FROM evm_wallets WHERE address = ? AND chain = ?",
        (address, chain)
    ).fetchone()
    
    if row:
        conn.close()
        return row[0]
    
    conn.execute(
        "INSERT INTO evm_wallets (address, chain) VALUES (?, ?)",
        (address, chain)
    )
    conn.commit()
    wallet_id = conn.execute(
        "SELECT id FROM evm_wallets WHERE address = ? AND chain = ?",
        (address, chain)
    ).fetchone()[0]
    conn.close()
    return wallet_id


def index_evm_address(address, chain="ethereum"):
    """Index all transactions for an EVM address."""
    print(f"\nIndexing {chain}: {address}")
    
    indexer = EVMIndexer(chain)
    wallet_id = get_or_create_evm_wallet(address, chain)
    conn = get_connection()
    
    total = 0
    
    # Normal transactions
    print(f"  Fetching normal transactions...")
    txs = indexer.get_normal_transactions(address)
    if isinstance(txs, list):
        for tx in txs:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO evm_transactions
                    (tx_hash, wallet_id, chain, block_number, block_timestamp,
                     from_address, to_address, value, gas_used, gas_price,
                     tx_type, success)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tx.get("hash"),
                    wallet_id,
                    chain,
                    int(tx.get("blockNumber", 0)),
                    int(tx.get("timeStamp", 0)),
                    tx.get("from", "").lower(),
                    tx.get("to", "").lower(),
                    tx.get("value", "0"),
                    tx.get("gasUsed", "0"),
                    tx.get("gasPrice", "0"),
                    "normal",
                    tx.get("isError", "0") == "0"
                ))
            except Exception as e:
                print(f"    Error: {e}")
        total += len(txs)
        print(f"    Found {len(txs)} normal transactions")
    
    conn.commit()
    
    # ERC20 transfers
    print(f"  Fetching ERC20 transfers...")
    txs = indexer.get_erc20_transfers(address)
    if isinstance(txs, list):
        for tx in txs:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO evm_transactions
                    (tx_hash, wallet_id, chain, block_number, block_timestamp,
                     from_address, to_address, value, tx_type,
                     token_symbol, token_decimal, token_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tx.get("hash"),
                    wallet_id,
                    chain,
                    int(tx.get("blockNumber", 0)),
                    int(tx.get("timeStamp", 0)),
                    tx.get("from", "").lower(),
                    tx.get("to", "").lower(),
                    tx.get("value", "0"),
                    "erc20",
                    tx.get("tokenSymbol", ""),
                    int(tx.get("tokenDecimal", 18)),
                    tx.get("value", "0")
                ))
            except Exception as e:
                pass  # Duplicates expected
        total += len(txs)
        print(f"    Found {len(txs)} ERC20 transfers")
    
    conn.commit()
    conn.close()
    
    # Get balance
    balance = indexer.get_balance(address)
    print(f"  Current balance: {balance:.6f} {chain.upper()[:3]}")
    
    return total


def index_all_evm():
    """Index all configured EVM addresses."""
    # From wallets.json
    addresses = [
        ("0x9d0CbF9350B9aE05cf84e91f0f17643cD3C63E75", ["ethereum"]),
        ("0x55b8e2c4AE5951D1A8e77d0E513a6E598Ee0bE86", ["ethereum", "polygon", "optimism"])
    ]
    
    total = 0
    for address, chains in addresses:
        for chain in chains:
            try:
                count = index_evm_address(address, chain)
                total += count
            except Exception as e:
                print(f"  Error indexing {chain}/{address}: {e}")
    
    print(f"\nTotal EVM transactions indexed: {total}")
    return total


if __name__ == "__main__":
    from db.init import init_db
    init_db()
    index_all_evm()
