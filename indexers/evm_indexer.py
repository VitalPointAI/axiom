#!/usr/bin/env python3
"""
EVM Chain Transaction Indexer
Supports Ethereum, Polygon, Optimism via Etherscan API V2.

Updated Feb 2026: Etherscan deprecated V1 API (Aug 2025).
Now uses unified V2 endpoint with chainid parameter.
"""

import time
import requests
from pathlib import Path
from typing import Optional, Dict, List, Any
from decimal import Decimal
import sys
import os

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from config import RATE_LIMIT_DELAY, MAX_RETRIES

# Etherscan API V2 - single endpoint for all chains
ETHERSCAN_V2_URL = 'https://api.etherscan.io/v2/api'

# Chain configurations with chain IDs for V2 API
# Free tier: ETH (1), Polygon (137) supported
# Paid tier required: Optimism (10), Arbitrum (42161), Base (8453)
# Cronos uses separate API at cronos.org/explorer/api
CHAIN_CONFIG = {
    'ETH': {
        'name': 'Ethereum',
        'chainid': 1,
        'decimals': 18,
        'symbol': 'ETH',
        'free_tier': True,
    },
    'Polygon': {
        'name': 'Polygon',
        'chainid': 137,
        'decimals': 18,
        'symbol': 'MATIC',
        'free_tier': True,
    },
    'Cronos': {
        'name': 'Cronos',
        'chainid': 25,
        'decimals': 18,
        'symbol': 'CRO',
        'free_tier': True,
        'custom_api': 'https://cronos.org/explorer/api',
        'api_key_env': 'CRONOS_API_KEY',
    },
    'Optimism': {
        'name': 'Optimism',
        'chainid': 10,
        'decimals': 18,
        'symbol': 'ETH',
        'free_tier': False,  # Requires paid API plan
    },
    'Arbitrum': {
        'name': 'Arbitrum',
        'chainid': 42161,
        'decimals': 18,
        'symbol': 'ETH',
        'free_tier': False,
    },
    'Base': {
        'name': 'Base',
        'chainid': 8453,
        'decimals': 18,
        'symbol': 'ETH',
        'free_tier': False,
    },
}

# Rate limiting for Etherscan free tier (5/sec, but be conservative)
EVM_RATE_LIMIT_DELAY = 0.25  # 4 requests per second max


class EVMIndexer:
    """
    Indexes EVM chain transactions using Etherscan API V2.
    """
    
    def __init__(self, chain: str, api_key: Optional[str] = None):
        if chain not in CHAIN_CONFIG:
            raise ValueError(f"Unsupported chain: {chain}. Supported: {list(CHAIN_CONFIG.keys())}")
        
        self.chain = chain
        self.config = CHAIN_CONFIG[chain]
        self.api_key = api_key or os.environ.get('ETHERSCAN_API_KEY')
        self.last_request_time = 0
        self.request_count = 0
        
        if not self.config['free_tier'] and not api_key:
            print(f"  Warning: {chain} requires a paid Etherscan API plan")
    
    def _wait_for_rate_limit(self):
        """Ensure minimum delay between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < EVM_RATE_LIMIT_DELAY:
            time.sleep(EVM_RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()
    
    def _request(self, params: Dict[str, str], retries: int = 0) -> Dict:
        """Make API request with rate limiting using V2 endpoint or custom API."""
        self._wait_for_rate_limit()
        self.request_count += 1
        
        # Determine API URL - use custom API for chains like Cronos
        if 'custom_api' in self.config:
            api_url = self.config['custom_api']
            # Use chain-specific API key if available
            api_key_env = self.config.get('api_key_env', 'ETHERSCAN_API_KEY')
            api_key = os.environ.get(api_key_env) or self.api_key
            if api_key:
                params['apikey'] = api_key
        else:
            api_url = ETHERSCAN_V2_URL
            # Add chainid and API key for Etherscan V2
            params['chainid'] = str(self.config['chainid'])
            if self.api_key:
                params['apikey'] = self.api_key
        
        try:
            response = requests.get(api_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Check for rate limit or paid tier errors
            if data.get('status') == '0':
                msg = data.get('result', '') or data.get('message', '')
                if 'rate limit' in msg.lower():
                    if retries < MAX_RETRIES:
                        wait_time = RATE_LIMIT_DELAY * (2 ** retries)
                        print(f"  Rate limited, waiting {wait_time:.1f}s (retry {retries+1}/{MAX_RETRIES})")
                        time.sleep(wait_time)
                        return self._request(params, retries + 1)
                    raise Exception("Rate limit exceeded")
                elif 'not supported' in msg.lower() or 'upgrade' in msg.lower():
                    raise Exception(f"Chain requires paid API plan: {msg}")
            
            return data
        except requests.exceptions.RequestException as e:
            if retries < MAX_RETRIES:
                time.sleep(RATE_LIMIT_DELAY)
                return self._request(params, retries + 1)
            raise
    
    def get_balance(self, address: str) -> Decimal:
        """Get native token balance."""
        params = {
            'module': 'account',
            'action': 'balance',
            'address': address,
        }
        data = self._request(params)
        if data.get('status') == '1':
            return Decimal(data['result']) / Decimal(10 ** self.config['decimals'])
        return Decimal(0)
    
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


def get_evm_wallet_id(address: str, chain: str) -> int:
    """Get or create EVM wallet record."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM evm_wallets WHERE address = ? AND chain = ?", 
        (address.lower(), chain.lower())
    ).fetchone()
    
    if row:
        conn.close()
        return row[0]
    
    # Create new wallet
    conn.execute(
        "INSERT INTO evm_wallets (address, chain, label, is_owned) VALUES (?, ?, ?, 1)", 
        (address.lower(), chain.lower(), f'{chain} Wallet')
    )
    conn.commit()
    wallet_id = conn.execute(
        "SELECT id FROM evm_wallets WHERE address = ? AND chain = ?", 
        (address.lower(), chain.lower())
    ).fetchone()[0]
    conn.close()
    return wallet_id


def get_last_evm_block(wallet_id: int, chain: str) -> int:
    """Get the last indexed block for incremental sync."""
    conn = get_connection()
    row = conn.execute(
        "SELECT last_block FROM evm_indexing_progress WHERE wallet_id = ? AND chain = ?",
        (wallet_id, chain.lower())
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def update_evm_progress(wallet_id: int, chain: str, block: int, total_fetched: int = 0):
    """Update indexing progress."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO evm_indexing_progress (wallet_id, chain, last_block, total_fetched, status, updated_at)
        VALUES (?, ?, ?, ?, 'complete', datetime('now'))
        ON CONFLICT(wallet_id) DO UPDATE SET 
            last_block = ?, 
            total_fetched = total_fetched + ?,
            status = 'complete',
            updated_at = datetime('now')
    """, (wallet_id, chain.lower(), block, total_fetched, block, total_fetched))
    conn.commit()
    conn.close()


def index_evm_account(address: str, chain: str, api_key: Optional[str] = None, force: bool = False) -> int:
    """
    Index all transactions for an EVM account.
    
    Returns: total transactions indexed
    """
    indexer = EVMIndexer(chain, api_key)
    wallet_id = get_evm_wallet_id(address, chain)
    config = CHAIN_CONFIG[chain]
    
    # Get starting block for incremental sync
    start_block = 0 if force else get_last_evm_block(wallet_id, chain) + 1
    
    print(f"{address} ({chain}): Starting from block {start_block}")
    
    total_indexed = 0
    max_block = start_block
    
    try:
        # Check balance first
        balance = indexer.get_balance(address)
        print(f"  Current balance: {balance:.6f} {config['symbol']}")
        
        # 1. Normal transactions
        print(f"  Fetching normal transactions...")
        normal_txs = indexer.get_normal_transactions(address, start_block)
        print(f"  Found {len(normal_txs)} normal transactions")
        
        conn = get_connection()
        for tx in normal_txs:
            block_num = int(tx['blockNumber'])
            max_block = max(max_block, block_num)
            
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO evm_transactions 
                    (tx_hash, wallet_id, chain, block_number, block_timestamp,
                     from_address, to_address, value, gas_used, gas_price,
                     tx_type, token_symbol, success, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tx['hash'],
                    wallet_id,
                    chain.lower(),
                    block_num,
                    int(tx['timeStamp']),
                    tx['from'].lower(),
                    (tx.get('to') or '').lower(),
                    tx.get('value', '0'),
                    tx.get('gasUsed', '0'),
                    tx.get('gasPrice', '0'),
                    'transfer',
                    config['symbol'],
                    tx.get('isError', '0') == '0',
                    str(tx)[:10000]
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting tx {tx['hash'][:16]}...: {e}")
        
        conn.commit()
        
        # 2. Internal transactions (contract calls with value)
        print(f"  Fetching internal transactions...")
        internal_txs = indexer.get_internal_transactions(address, start_block)
        print(f"  Found {len(internal_txs)} internal transactions")
        
        for tx in internal_txs:
            block_num = int(tx.get('blockNumber', 0))
            max_block = max(max_block, block_num)
            
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO evm_transactions 
                    (tx_hash, wallet_id, chain, block_number, block_timestamp,
                     from_address, to_address, value, gas_used, gas_price,
                     tx_type, token_symbol, success, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"{tx.get('hash', 'unknown')}-internal-{tx.get('traceId', 0)}",
                    wallet_id,
                    chain.lower(),
                    block_num,
                    int(tx.get('timeStamp', 0)),
                    (tx.get('from') or '').lower(),
                    (tx.get('to') or '').lower(),
                    tx.get('value', '0'),
                    '0',  # Internal txs don't have separate gas
                    '0',
                    'internal',
                    config['symbol'],
                    tx.get('isError', '0') == '0',
                    str(tx)[:10000]
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting internal tx: {e}")
        
        conn.commit()
        
        # 3. ERC20 token transfers
        print(f"  Fetching ERC20 transfers...")
        erc20_txs = indexer.get_erc20_transfers(address, start_block)
        print(f"  Found {len(erc20_txs)} ERC20 transfers")
        
        for tx in erc20_txs:
            block_num = int(tx['blockNumber'])
            max_block = max(max_block, block_num)
            decimals = int(tx.get('tokenDecimal', 18))
            
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO evm_transactions 
                    (tx_hash, wallet_id, chain, block_number, block_timestamp,
                     from_address, to_address, value, gas_used, gas_price,
                     tx_type, token_symbol, token_decimal, token_value, success, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"{tx['hash']}-{tx.get('tokenSymbol', 'ERC20')}-{tx.get('logIndex', 0)}",
                    wallet_id,
                    chain.lower(),
                    block_num,
                    int(tx['timeStamp']),
                    tx['from'].lower(),
                    tx['to'].lower(),
                    '0',  # Native value is 0 for token transfers
                    '0',  # Gas already counted in normal tx
                    '0',
                    'erc20',
                    tx.get('tokenSymbol', 'UNKNOWN'),
                    decimals,
                    tx.get('value', '0'),  # Raw token value
                    True,
                    str(tx)[:10000]
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting ERC20 tx: {e}")
        
        conn.commit()
        
        # 4. NFT transfers (ERC721)
        print(f"  Fetching NFT transfers...")
        nft_txs = indexer.get_erc721_transfers(address, start_block)
        print(f"  Found {len(nft_txs)} NFT transfers")
        
        for tx in nft_txs:
            block_num = int(tx['blockNumber'])
            max_block = max(max_block, block_num)
            
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO evm_transactions 
                    (tx_hash, wallet_id, chain, block_number, block_timestamp,
                     from_address, to_address, value, gas_used, gas_price,
                     tx_type, token_symbol, token_value, success, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"{tx['hash']}-NFT-{tx.get('tokenID', 0)}",
                    wallet_id,
                    chain.lower(),
                    block_num,
                    int(tx['timeStamp']),
                    tx['from'].lower(),
                    tx['to'].lower(),
                    '0',
                    '0',
                    '0',
                    'nft',
                    tx.get('tokenSymbol', 'NFT'),
                    tx.get('tokenID', '0'),  # Store token ID
                    True,
                    str(tx)[:10000]
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting NFT tx: {e}")
        
        conn.commit()
        conn.close()
        
        # Update progress
        if max_block > start_block:
            update_evm_progress(wallet_id, chain, max_block, total_indexed)
        
        print(f"{address} ({chain}): Complete! {total_indexed} transactions indexed")
        return total_indexed
        
    except Exception as e:
        print(f"{address} ({chain}): Error - {e}")
        raise


def sync_all_evm_wallets(api_key: Optional[str] = None, force: bool = False):
    """Sync all EVM wallets in the database."""
    conn = get_connection()
    wallets = conn.execute(
        "SELECT address, chain FROM evm_wallets WHERE is_owned = 1 ORDER BY chain, address"
    ).fetchall()
    conn.close()
    
    # Map DB chain names to indexer chain names
    chain_map = {
        'ethereum': 'ETH',
        'polygon': 'Polygon',
        'optimism': 'Optimism',
        'arbitrum': 'Arbitrum',
        'base': 'Base',
    }
    
    print(f"Syncing {len(wallets)} EVM wallets...")
    total = 0
    
    for address, db_chain in wallets:
        chain = chain_map.get(db_chain.lower(), db_chain)
        
        # Skip unsupported chains on free tier
        if chain in CHAIN_CONFIG and not CHAIN_CONFIG[chain]['free_tier']:
            print(f"\nSkipping {address[:10]}... ({chain}) - requires paid API plan")
            continue
        
        try:
            count = index_evm_account(address, chain, api_key, force)
            total += count
        except Exception as e:
            print(f"  Error syncing {address[:10]}... ({chain}): {e}")
    
    print(f"\n=== Total: {total} transactions indexed ===")
    return total


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) == 1 or sys.argv[1] == '--all':
        # Sync all wallets
        force = '--force' in sys.argv
        sync_all_evm_wallets(force=force)
    elif len(sys.argv) >= 3:
        address = sys.argv[1]
        chain = sys.argv[2]
        force = '--force' in sys.argv
        
        try:
            count = index_evm_account(address, chain, force=force)
            print(f"\nIndexed {count} transactions")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print("Usage:")
        print("  python evm_indexer.py --all [--force]     # Sync all wallets")
        print("  python evm_indexer.py <address> <chain> [--force]")
        print("Chains: ETH, Polygon, Optimism (paid), Arbitrum (paid), Base (paid)")
        sys.exit(1)
