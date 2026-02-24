#!/usr/bin/env python3
"""
EVM Chain Transaction Indexer
Supports Ethereum, Polygon, Optimism via Etherscan-family APIs.
"""

import time
import requests
from pathlib import Path
from typing import Optional, Dict, List, Any
from decimal import Decimal
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from config import RATE_LIMIT_DELAY, MAX_RETRIES

# Etherscan-family API endpoints (free tier: 5 calls/sec)
CHAIN_CONFIG = {
    'ETH': {
        'name': 'Ethereum',
        'api_url': 'https://api.etherscan.io/api',
        'api_key_env': 'ETHERSCAN_API_KEY',
        'decimals': 18,
        'symbol': 'ETH',
    },
    'Polygon': {
        'name': 'Polygon',
        'api_url': 'https://api.polygonscan.com/api',
        'api_key_env': 'POLYGONSCAN_API_KEY',
        'decimals': 18,
        'symbol': 'MATIC',
    },
    'Optimism': {
        'name': 'Optimism',
        'api_url': 'https://api-optimistic.etherscan.io/api',
        'api_key_env': 'OPTIMISM_API_KEY',
        'decimals': 18,
        'symbol': 'ETH',
    },
}

# Rate limiting for Etherscan free tier (5/sec, but be conservative)
EVM_RATE_LIMIT_DELAY = 0.25  # 4 requests per second max


class EVMIndexer:
    """
    Indexes EVM chain transactions using Etherscan-family APIs.
    """
    
    def __init__(self, chain: str, api_key: Optional[str] = None):
        if chain not in CHAIN_CONFIG:
            raise ValueError(f"Unsupported chain: {chain}. Supported: {list(CHAIN_CONFIG.keys())}")
        
        self.chain = chain
        self.config = CHAIN_CONFIG[chain]
        self.api_key = api_key or self._get_api_key()
        self.last_request_time = 0
        self.request_count = 0
    
    def _get_api_key(self) -> Optional[str]:
        """Get API key from environment."""
        import os
        return os.environ.get(self.config['api_key_env'])
    
    def _wait_for_rate_limit(self):
        """Ensure minimum delay between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < EVM_RATE_LIMIT_DELAY:
            time.sleep(EVM_RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()
    
    def _request(self, params: Dict[str, str], retries: int = 0) -> Dict:
        """Make API request with rate limiting."""
        self._wait_for_rate_limit()
        self.request_count += 1
        
        if self.api_key:
            params['apikey'] = self.api_key
        
        try:
            response = requests.get(self.config['api_url'], params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Check for rate limit error
            if data.get('status') == '0' and 'rate limit' in data.get('message', '').lower():
                if retries < MAX_RETRIES:
                    wait_time = RATE_LIMIT_DELAY * (2 ** retries)
                    print(f"  Rate limited, waiting {wait_time:.1f}s (retry {retries+1}/{MAX_RETRIES})")
                    time.sleep(wait_time)
                    return self._request(params, retries + 1)
                raise Exception("Rate limit exceeded")
            
            return data
        except requests.exceptions.RequestException as e:
            if retries < MAX_RETRIES:
                time.sleep(RATE_LIMIT_DELAY)
                return self._request(params, retries + 1)
            raise
    
    def get_normal_transactions(self, address: str, start_block: int = 0) -> List[Dict]:
        """Get normal (ETH/native) transactions."""
        params = {
            'module': 'account',
            'action': 'txlist',
            'address': address,
            'startblock': str(start_block),
            'endblock': '99999999',
            'sort': 'asc',
        }
        data = self._request(params)
        
        if data.get('status') == '1':
            return data.get('result', [])
        return []
    
    def get_internal_transactions(self, address: str, start_block: int = 0) -> List[Dict]:
        """Get internal transactions (contract calls with value)."""
        params = {
            'module': 'account',
            'action': 'txlistinternal',
            'address': address,
            'startblock': str(start_block),
            'endblock': '99999999',
            'sort': 'asc',
        }
        data = self._request(params)
        
        if data.get('status') == '1':
            return data.get('result', [])
        return []
    
    def get_erc20_transfers(self, address: str, start_block: int = 0) -> List[Dict]:
        """Get ERC20 token transfers."""
        params = {
            'module': 'account',
            'action': 'tokentx',
            'address': address,
            'startblock': str(start_block),
            'endblock': '99999999',
            'sort': 'asc',
        }
        data = self._request(params)
        
        if data.get('status') == '1':
            return data.get('result', [])
        return []
    
    def get_erc721_transfers(self, address: str, start_block: int = 0) -> List[Dict]:
        """Get ERC721 (NFT) transfers."""
        params = {
            'module': 'account',
            'action': 'tokennfttx',
            'address': address,
            'startblock': str(start_block),
            'endblock': '99999999',
            'sort': 'asc',
        }
        data = self._request(params)
        
        if data.get('status') == '1':
            return data.get('result', [])
        return []


def get_wallet_id(address: str, chain: str) -> int:
    """Get or create wallet record."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM wallets WHERE account_id = ? AND chain = ?", 
        (address.lower(), chain)
    ).fetchone()
    
    if row:
        conn.close()
        return row[0]
    
    conn.execute(
        "INSERT INTO wallets (account_id, chain, sync_status) VALUES (?, ?, 'pending')", 
        (address.lower(), chain)
    )
    conn.commit()
    wallet_id = conn.execute(
        "SELECT id FROM wallets WHERE account_id = ? AND chain = ?", 
        (address.lower(), chain)
    ).fetchone()[0]
    conn.close()
    return wallet_id


def get_last_block(wallet_id: int) -> int:
    """Get the last indexed block for incremental sync."""
    conn = get_connection()
    row = conn.execute(
        "SELECT MAX(block_height) FROM transactions WHERE wallet_id = ?",
        (wallet_id,)
    ).fetchone()
    conn.close()
    return row[0] if row[0] else 0


def index_evm_account(address: str, chain: str, api_key: Optional[str] = None, force: bool = False) -> int:
    """
    Index all transactions for an EVM account.
    
    Returns: total transactions indexed
    """
    indexer = EVMIndexer(chain, api_key)
    wallet_id = get_wallet_id(address, chain)
    config = CHAIN_CONFIG[chain]
    
    # Get starting block for incremental sync
    start_block = 0 if force else get_last_block(wallet_id) + 1
    
    print(f"{address} ({chain}): Starting from block {start_block}")
    
    # Update status
    conn = get_connection()
    conn.execute("UPDATE wallets SET sync_status = 'in_progress' WHERE id = ?", (wallet_id,))
    conn.commit()
    conn.close()
    
    total_indexed = 0
    
    try:
        # 1. Normal transactions
        print(f"  Fetching normal transactions...")
        normal_txs = indexer.get_normal_transactions(address, start_block)
        print(f"  Found {len(normal_txs)} normal transactions")
        
        conn = get_connection()
        for tx in normal_txs:
            direction = 'out' if tx['from'].lower() == address.lower() else 'in'
            counterparty = tx['to'] if direction == 'out' else tx['from']
            
            # Convert wei to native token
            amount = str(Decimal(tx.get('value', '0')) / Decimal(10 ** config['decimals']))
            fee = str(Decimal(tx.get('gasUsed', '0')) * Decimal(tx.get('gasPrice', '0')) / Decimal(10 ** 18))
            
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO transactions 
                    (tx_hash, wallet_id, direction, counterparty, action_type, method_name,
                     amount, fee, block_height, block_timestamp, success, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tx['hash'],
                    wallet_id,
                    direction,
                    counterparty,
                    'transfer',
                    tx.get('functionName', '').split('(')[0] or None,
                    amount,
                    fee,
                    int(tx['blockNumber']),
                    tx['timeStamp'],
                    tx.get('isError', '0') == '0',
                    str(tx)[:10000]
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting tx {tx['hash'][:16]}...: {e}")
        
        conn.commit()
        
        # 2. ERC20 token transfers
        print(f"  Fetching ERC20 transfers...")
        erc20_txs = indexer.get_erc20_transfers(address, start_block)
        print(f"  Found {len(erc20_txs)} ERC20 transfers")
        
        for tx in erc20_txs:
            direction = 'out' if tx['from'].lower() == address.lower() else 'in'
            counterparty = tx['to'] if direction == 'out' else tx['from']
            
            # Token amount with proper decimals
            decimals = int(tx.get('tokenDecimal', 18))
            amount = str(Decimal(tx.get('value', '0')) / Decimal(10 ** decimals))
            
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO transactions 
                    (tx_hash, wallet_id, direction, counterparty, action_type, method_name,
                     amount, fee, block_height, block_timestamp, success, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"{tx['hash']}-{tx.get('tokenSymbol', 'ERC20')}-{tx.get('logIndex', 0)}",
                    wallet_id,
                    direction,
                    counterparty,
                    'erc20_transfer',
                    tx.get('tokenSymbol', 'UNKNOWN'),
                    amount,
                    '0',  # Fee already counted in normal tx
                    int(tx['blockNumber']),
                    tx['timeStamp'],
                    True,
                    str(tx)[:10000]
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting ERC20 tx: {e}")
        
        conn.commit()
        
        # 3. NFT transfers (ERC721)
        print(f"  Fetching NFT transfers...")
        nft_txs = indexer.get_erc721_transfers(address, start_block)
        print(f"  Found {len(nft_txs)} NFT transfers")
        
        for tx in nft_txs:
            direction = 'out' if tx['from'].lower() == address.lower() else 'in'
            counterparty = tx['to'] if direction == 'out' else tx['from']
            
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO transactions 
                    (tx_hash, wallet_id, direction, counterparty, action_type, method_name,
                     amount, fee, block_height, block_timestamp, success, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"{tx['hash']}-NFT-{tx.get('tokenID', 0)}",
                    wallet_id,
                    direction,
                    counterparty,
                    'nft_transfer',
                    tx.get('tokenName', 'NFT'),
                    tx.get('tokenID', '0'),  # Store token ID as amount
                    '0',
                    int(tx['blockNumber']),
                    tx['timeStamp'],
                    True,
                    str(tx)[:10000]
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting NFT tx: {e}")
        
        conn.commit()
        conn.close()
        
        # Update wallet status
        conn = get_connection()
        conn.execute("""
            UPDATE wallets 
            SET sync_status = 'complete', last_synced_at = datetime('now')
            WHERE id = ?
        """, (wallet_id,))
        conn.commit()
        conn.close()
        
        print(f"{address} ({chain}): Complete! {total_indexed} transactions indexed")
        return total_indexed
        
    except Exception as e:
        conn = get_connection()
        conn.execute("UPDATE wallets SET sync_status = 'error' WHERE id = ?", (wallet_id,))
        conn.commit()
        conn.close()
        print(f"{address} ({chain}): Error - {e}")
        raise


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python evm_indexer.py <address> <chain> [--force]")
        print("Chains: ETH, Polygon, Optimism")
        sys.exit(1)
    
    address = sys.argv[1]
    chain = sys.argv[2]
    force = '--force' in sys.argv
    
    try:
        count = index_evm_account(address, chain, force=force)
        print(f"\nIndexed {count} transactions")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
