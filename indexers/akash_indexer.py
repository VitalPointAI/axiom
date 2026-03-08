#!/usr/bin/env python3
"""
Akash Network Transaction Indexer

Uses the Akash LCD/REST API (Cosmos SDK) to fetch transaction history.
No API key required - uses public endpoints.
"""

import time
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime
import sys
import os

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection

# Akash public LCD endpoints
AKASH_LCD_ENDPOINTS = [
    'https://api.akash.forbole.com',
    'https://akash-api.polkachu.com',
    'https://akash-rest.publicnode.com',
]

# Rate limiting
RATE_LIMIT_DELAY = 0.5  # 2 requests per second
MAX_RETRIES = 3

# AKT decimals
AKT_DECIMALS = 6  # 1 AKT = 1,000,000 uakt


class AkashIndexer:
    """
    Indexes Akash Network transactions using Cosmos LCD API.
    """
    
    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = endpoint or AKASH_LCD_ENDPOINTS[0]
        self.last_request_time = 0
        self.request_count = 0
    
    def _wait_for_rate_limit(self):
        """Ensure minimum delay between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()
    
    def _request(self, path: str, params: Dict = None, retries: int = 0) -> Dict:
        """Make REST request with rate limiting."""
        self._wait_for_rate_limit()
        self.request_count += 1
        
        url = f"{self.endpoint}{path}"
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            if retries < MAX_RETRIES:
                # Try a different endpoint
                endpoint_idx = (AKASH_LCD_ENDPOINTS.index(self.endpoint) + 1) % len(AKASH_LCD_ENDPOINTS)
                self.endpoint = AKASH_LCD_ENDPOINTS[endpoint_idx]
                print(f"  Switching to endpoint: {self.endpoint}")
                time.sleep(RATE_LIMIT_DELAY * (2 ** retries))
                return self._request(path, params, retries + 1)
            raise
    
    def get_account_balance(self, address: str) -> Dict[str, Decimal]:
        """Get account balances."""
        try:
            data = self._request(f'/cosmos/bank/v1beta1/balances/{address}')
            balances = {}
            
            for balance in data.get('balances', []):
                denom = balance.get('denom', 'uakt')
                amount = Decimal(balance.get('amount', '0'))
                
                # Convert uakt to AKT
                if denom == 'uakt':
                    balances['AKT'] = amount / Decimal(10 ** AKT_DECIMALS)
                else:
                    balances[denom] = amount
            
            return balances
        except Exception as e:
            print(f"  Error getting balance: {e}")
            return {}
    
    def get_account_transactions(
        self, 
        address: str, 
        pagination_key: Optional[str] = None,
        limit: int = 100
    ) -> Dict:
        """
        Get account transactions using tx search.
        Returns transactions and pagination info.
        """
        # Query transactions where address is sender or recipient
        params = {
            'events': f"message.sender='{address}'",
            'pagination.limit': str(limit),
            'order_by': 'ORDER_BY_DESC',
        }
        
        if pagination_key:
            params['pagination.key'] = pagination_key
        
        try:
            # Get sent transactions
            sent = self._request('/cosmos/tx/v1beta1/txs', params)
            
            # Get received transactions
            params['events'] = f"transfer.recipient='{address}'"
            received = self._request('/cosmos/tx/v1beta1/txs', params)
            
            # Merge and dedupe
            all_txs = {}
            for tx_resp in sent.get('tx_responses', []):
                all_txs[tx_resp.get('txhash', '')] = tx_resp
            for tx_resp in received.get('tx_responses', []):
                all_txs[tx_resp.get('txhash', '')] = tx_resp
            
            return {
                'tx_responses': list(all_txs.values()),
                'pagination': sent.get('pagination', {})
            }
            
        except Exception as e:
            print(f"  Error fetching transactions: {e}")
            return {'tx_responses': [], 'pagination': {}}
    
    def get_all_transactions(self, address: str, limit_pages: int = 50) -> List[Dict]:
        """
        Get all transactions for an account.
        Handles pagination automatically.
        """
        all_txs = []
        pagination_key = None
        page = 0
        
        while page < limit_pages:
            result = self.get_account_transactions(address, pagination_key)
            
            txs = result.get('tx_responses', [])
            if not txs:
                break
            
            all_txs.extend(txs)
            page += 1
            
            # Check for more pages
            pagination = result.get('pagination', {})
            pagination_key = pagination.get('next_key')
            if not pagination_key:
                break
            
            print(f"    Fetched {len(all_txs)} transactions (page {page})...")
        
        return all_txs


def uakt_to_akt(uakt: str) -> Decimal:
    """Convert uakt to AKT."""
    return Decimal(uakt) / Decimal(10 ** AKT_DECIMALS)


def get_akash_wallet_id(address: str) -> int:
    """Get or create Akash wallet record."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM akash_wallets WHERE address = %s", 
        (address,)
    ).fetchone()
    
    if row:
        conn.close()
        return row[0]
    
    # Create new wallet
    conn.execute(
        "INSERT INTO akash_wallets (address, label, is_owned) VALUES (%s, %s, TRUE)", 
        (address, 'Akash Wallet')
    )
    conn.commit()
    wallet_id = conn.execute(
        "SELECT id FROM akash_wallets WHERE address = %s", 
        (address,)
    ).fetchone()[0]
    conn.close()
    return wallet_id


def get_last_akash_height(wallet_id: int) -> int:
    """Get the last indexed block height for incremental sync."""
    conn = get_connection()
    row = conn.execute(
        "SELECT last_height FROM akash_indexing_progress WHERE wallet_id = %s",
        (wallet_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def update_akash_progress(wallet_id: int, height: int, total_fetched: int = 0):
    """Update indexing progress."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO akash_indexing_progress (wallet_id, last_height, total_fetched, status, updated_at)
        VALUES (%s, %s, %s, 'complete', NOW())
        ON CONFLICT(wallet_id) DO UPDATE SET 
            last_height = EXCLUDED.last_height,
            total_fetched = akash_indexing_progress.total_fetched + EXCLUDED.total_fetched,
            status = 'complete',
            updated_at = NOW()
    """, (wallet_id, height, total_fetched))
    conn.commit()
    conn.close()


def parse_akash_transaction(tx_resp: Dict, wallet_address: str) -> Dict:
    """Parse Cosmos tx_response into normalized format."""
    tx_hash = tx_resp.get('txhash', '')
    height = int(tx_resp.get('height', 0))
    timestamp = tx_resp.get('timestamp', '')
    
    # Parse timestamp
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        unix_timestamp = int(dt.timestamp())
    except:
        unix_timestamp = 0
    
    # Determine transaction type from messages
    tx = tx_resp.get('tx', {})
    body = tx.get('body', {})
    messages = body.get('messages', [])
    
    tx_type = 'unknown'
    sender = ''
    recipient = ''
    amount = Decimal(0)
    denom = 'uakt'
    
    for msg in messages:
        msg_type = msg.get('@type', '')
        
        if 'MsgSend' in msg_type:
            tx_type = 'transfer'
            sender = msg.get('from_address', '')
            recipient = msg.get('to_address', '')
            amounts = msg.get('amount', [])
            if amounts:
                amount = Decimal(amounts[0].get('amount', '0'))
                denom = amounts[0].get('denom', 'uakt')
        
        elif 'MsgDelegate' in msg_type:
            tx_type = 'delegate'
            sender = msg.get('delegator_address', '')
            recipient = msg.get('validator_address', '')
            amt = msg.get('amount', {})
            amount = Decimal(amt.get('amount', '0'))
            denom = amt.get('denom', 'uakt')
        
        elif 'MsgUndelegate' in msg_type:
            tx_type = 'undelegate'
            sender = msg.get('delegator_address', '')
            recipient = msg.get('validator_address', '')
            amt = msg.get('amount', {})
            amount = Decimal(amt.get('amount', '0'))
            denom = amt.get('denom', 'uakt')
        
        elif 'MsgWithdrawDelegatorReward' in msg_type:
            tx_type = 'claim_rewards'
            sender = msg.get('delegator_address', '')
            recipient = msg.get('validator_address', '')
        
        elif 'MsgCreateDeployment' in msg_type:
            tx_type = 'create_deployment'
            sender = msg.get('owner', '') or msg.get('id', {}).get('owner', '')
        
        elif 'MsgCloseDeployment' in msg_type:
            tx_type = 'close_deployment'
            sender = msg.get('id', {}).get('owner', '')
    
    # Direction
    is_outgoing = sender.lower() == wallet_address.lower()
    
    # Fee
    auth_info = tx.get('auth_info', {})
    fee_info = auth_info.get('fee', {})
    fee_amounts = fee_info.get('amount', [])
    fee = Decimal(0)
    if fee_amounts:
        fee = Decimal(fee_amounts[0].get('amount', '0'))
    
    # Success
    code = tx_resp.get('code', 0)
    success = code == 0
    
    return {
        'tx_hash': tx_hash,
        'height': height,
        'timestamp': unix_timestamp,
        'tx_type': tx_type,
        'sender': sender,
        'recipient': recipient,
        'is_outgoing': is_outgoing,
        'amount': amount,
        'denom': denom,
        'fee': fee,
        'success': success,
        'raw_json': str(tx_resp)[:10000]
    }


def index_akash_account(address: str, force: bool = False) -> int:
    """
    Index all transactions for an Akash account.
    Returns: total transactions indexed
    """
    indexer = AkashIndexer()
    wallet_id = get_akash_wallet_id(address)
    
    # Get starting height for incremental sync
    start_height = 0 if force else get_last_akash_height(wallet_id)
    
    print(f"{address}: Starting from height {start_height}")
    
    try:
        # Check balance first
        balances = indexer.get_account_balance(address)
        for denom, amount in balances.items():
            print(f"  Balance: {amount:.6f} {denom}")
        
        if not balances:
            print(f"  Balance: 0 AKT")
        
        # Fetch transactions
        print(f"  Fetching transactions...")
        txs = indexer.get_all_transactions(address)
        print(f"  Found {len(txs)} transactions")
        
        if not txs:
            print(f"{address}: No new transactions")
            return 0
        
        conn = get_connection()
        total_indexed = 0
        max_height = start_height
        
        for tx_resp in txs:
            parsed = parse_akash_transaction(tx_resp, address)
            
            # Skip if before start height
            if parsed['height'] <= start_height:
                continue
            
            max_height = max(max_height, parsed['height'])
            
            try:
                conn.execute("""
                    INSERT INTO akash_transactions 
                    (tx_hash, wallet_id, height, block_timestamp,
                     tx_type, sender, recipient, is_outgoing,
                     amount, denom, fee, success, raw_json)
                    VALUES (%s, %s, %s, to_timestamp(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tx_hash) DO NOTHING
                """, (
                    parsed['tx_hash'],
                    wallet_id,
                    parsed['height'],
                    parsed['timestamp'],
                    parsed['tx_type'],
                    parsed['sender'],
                    parsed['recipient'],
                    parsed['is_outgoing'],
                    str(parsed['amount']),
                    parsed['denom'],
                    str(parsed['fee']),
                    parsed['success'],
                    parsed['raw_json']
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting tx {parsed['tx_hash'][:16]}...: {e}")
        
        conn.commit()
        conn.close()
        
        # Update progress
        if max_height > start_height:
            update_akash_progress(wallet_id, max_height, total_indexed)
        
        print(f"{address}: Complete! {total_indexed} transactions indexed")
        return total_indexed
        
    except Exception as e:
        print(f"{address}: Error - {e}")
        raise


def ensure_akash_tables():
    """Create Akash-specific tables if they don't exist."""
    conn = get_connection()
    
    # Akash wallets table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS akash_wallets (
            id SERIAL PRIMARY KEY,
            address VARCHAR(100) UNIQUE NOT NULL,
            label VARCHAR(255),
            is_owned BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Akash transactions table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS akash_transactions (
            id SERIAL PRIMARY KEY,
            tx_hash VARCHAR(128) UNIQUE NOT NULL,
            wallet_id INTEGER REFERENCES akash_wallets(id),
            height BIGINT,
            block_timestamp TIMESTAMP,
            tx_type VARCHAR(50),
            sender VARCHAR(100),
            recipient VARCHAR(100),
            is_outgoing BOOLEAN,
            amount DECIMAL(30, 10),
            denom VARCHAR(50),
            fee DECIMAL(20, 10),
            success BOOLEAN,
            raw_json TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Indexing progress table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS akash_indexing_progress (
            wallet_id INTEGER PRIMARY KEY REFERENCES akash_wallets(id),
            last_height BIGINT DEFAULT 0,
            total_fetched INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'pending',
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    conn.commit()
    conn.close()
    print("Akash tables ensured")


def sync_all_akash_wallets(force: bool = False) -> int:
    """Sync all Akash wallets in the database."""
    conn = get_connection()
    wallets = conn.execute(
        "SELECT address FROM akash_wallets WHERE is_owned = TRUE ORDER BY address"
    ).fetchall()
    conn.close()
    
    print(f"Syncing {len(wallets)} Akash wallets...")
    total = 0
    
    for (address,) in wallets:
        try:
            count = index_akash_account(address, force)
            total += count
        except Exception as e:
            print(f"  Error syncing {address}: {e}")
    
    print(f"\n=== Total: {total} Akash transactions indexed ===")
    return total


if __name__ == "__main__":
    import sys
    
    # Ensure tables exist
    ensure_akash_tables()
    
    if len(sys.argv) == 1 or sys.argv[1] == '--all':
        # Sync all wallets
        force = '--force' in sys.argv
        sync_all_akash_wallets(force=force)
    elif len(sys.argv) >= 2 and sys.argv[1] != '--all':
        address = sys.argv[1]
        force = '--force' in sys.argv
        
        try:
            count = index_akash_account(address, force=force)
            print(f"\nIndexed {count} transactions")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print("Usage:")
        print("  python akash_indexer.py --all [--force]     # Sync all wallets")
        print("  python akash_indexer.py <address> [--force]  # Sync specific address")
        print("  Akash addresses start with 'akash1'")
        sys.exit(1)
