#!/usr/bin/env python3
"""
XRP Ledger Transaction Indexer

Uses the public XRPL API to fetch transaction history.
No API key required - uses public JSON-RPC endpoint.
"""

import time
import requests
from pathlib import Path
from typing import Optional, List, Dict
from decimal import Decimal
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection

# XRPL public endpoints (mainnet)
XRPL_ENDPOINTS = [
    'https://xrplcluster.com',
    'https://s1.ripple.com:51234',
    'https://s2.ripple.com:51234',
]

# Rate limiting
RATE_LIMIT_DELAY = 0.5  # 2 requests per second
MAX_RETRIES = 3

# XRP decimals (drops)
XRP_DECIMALS = 6  # 1 XRP = 1,000,000 drops


class XRPIndexer:
    """
    Indexes XRP Ledger transactions using public JSON-RPC API.
    """
    
    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = endpoint or XRPL_ENDPOINTS[0]
        self.last_request_time = 0
        self.request_count = 0
    
    def _wait_for_rate_limit(self):
        """Ensure minimum delay between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()
    
    def _request(self, method: str, params: Dict, retries: int = 0) -> Dict:
        """Make JSON-RPC request with rate limiting."""
        self._wait_for_rate_limit()
        self.request_count += 1
        
        payload = {
            "method": method,
            "params": [params]
        }
        
        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if 'result' in data:
                result = data['result']
                if result.get('status') == 'error':
                    error = result.get('error', 'Unknown error')
                    error_msg = result.get('error_message', '')
                    raise Exception(f"XRPL error: {error} - {error_msg}")
                return result
            
            return data
            
        except requests.exceptions.RequestException:
            if retries < MAX_RETRIES:
                # Try a different endpoint
                endpoint_idx = (XRPL_ENDPOINTS.index(self.endpoint) + 1) % len(XRPL_ENDPOINTS)
                self.endpoint = XRPL_ENDPOINTS[endpoint_idx]
                print(f"  Switching to endpoint: {self.endpoint}")
                time.sleep(RATE_LIMIT_DELAY * (2 ** retries))
                return self._request(method, params, retries + 1)
            raise
    
    def get_account_info(self, address: str) -> Dict:
        """Get account information including balance."""
        result = self._request('account_info', {
            'account': address,
            'ledger_index': 'validated'
        })
        return result.get('account_data', {})
    
    def get_account_transactions(
        self, 
        address: str, 
        marker: Optional[Dict] = None,
        limit: int = 200
    ) -> Dict:
        """
        Get account transaction history.
        Returns transactions and marker for pagination.
        """
        params = {
            'account': address,
            'ledger_index_min': -1,
            'ledger_index_max': -1,
            'binary': False,
            'forward': False,  # Most recent first
            'limit': limit
        }
        
        if marker:
            params['marker'] = marker
        
        return self._request('account_tx', params)
    
    def get_all_transactions(self, address: str, since_ledger: int = 0) -> List[Dict]:
        """
        Get all transactions for an account.
        Handles pagination automatically.
        """
        all_txs = []
        marker = None
        
        while True:
            result = self.get_account_transactions(address, marker)
            
            txs = result.get('transactions', [])
            if not txs:
                break
            
            # Filter by ledger index if needed
            if since_ledger > 0:
                txs = [tx for tx in txs if tx.get('tx', {}).get('ledger_index', 0) > since_ledger]
            
            all_txs.extend(txs)
            
            # Check for more pages
            marker = result.get('marker')
            if not marker:
                break
            
            print(f"    Fetched {len(all_txs)} transactions so far...")
        
        return all_txs


def drops_to_xrp(drops: str) -> Decimal:
    """Convert drops to XRP."""
    return Decimal(drops) / Decimal(10 ** XRP_DECIMALS)


def ripple_time_to_unix(ripple_time: int) -> int:
    """Convert Ripple epoch time to Unix timestamp."""
    # Ripple epoch starts Jan 1, 2000 00:00:00 UTC
    RIPPLE_EPOCH = 946684800
    return ripple_time + RIPPLE_EPOCH


def get_xrp_wallet_id(address: str) -> int:
    """Get or create XRP wallet record."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM xrp_wallets WHERE address = ?", 
        (address,)
    ).fetchone()
    
    if row:
        conn.close()
        return row[0]
    
    # Create new wallet
    conn.execute(
        "INSERT INTO xrp_wallets (address, label, is_owned) VALUES (?, ?, 1)", 
        (address, 'XRP Wallet')
    )
    conn.commit()
    wallet_id = conn.execute(
        "SELECT id FROM xrp_wallets WHERE address = ?", 
        (address,)
    ).fetchone()[0]
    conn.close()
    return wallet_id


def get_last_xrp_ledger(wallet_id: int) -> int:
    """Get the last indexed ledger for incremental sync."""
    conn = get_connection()
    row = conn.execute(
        "SELECT last_ledger FROM xrp_indexing_progress WHERE wallet_id = ?",
        (wallet_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def update_xrp_progress(wallet_id: int, ledger: int, total_fetched: int = 0):
    """Update indexing progress."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO xrp_indexing_progress (wallet_id, last_ledger, total_fetched, status, updated_at)
        VALUES (?, ?, ?, 'complete', NOW())
        ON CONFLICT(wallet_id) DO UPDATE SET 
            last_ledger = EXCLUDED.last_ledger,
            total_fetched = xrp_indexing_progress.total_fetched + EXCLUDED.total_fetched,
            status = 'complete',
            updated_at = NOW()
    """, (wallet_id, ledger, total_fetched))
    conn.commit()
    conn.close()


def parse_xrp_transaction(tx_data: Dict, wallet_address: str) -> Dict:
    """Parse XRPL transaction into normalized format."""
    tx = tx_data.get('tx', {})
    meta = tx_data.get('meta', {})
    
    tx_type = tx.get('TransactionType', 'Unknown')
    tx_hash = tx.get('hash', '')
    ledger = tx.get('ledger_index', 0)
    timestamp = ripple_time_to_unix(tx.get('date', 0))
    
    sender = tx.get('Account', '')
    destination = tx.get('Destination', '')
    
    # Determine direction
    is_outgoing = sender.lower() == wallet_address.lower()
    
    # Parse amount (can be XRP drops or issued currency)
    amount_raw = tx.get('Amount', '0')
    if isinstance(amount_raw, str):
        # Native XRP in drops
        amount = drops_to_xrp(amount_raw)
        currency = 'XRP'
        issuer = None
    elif isinstance(amount_raw, dict):
        # Issued currency
        amount = Decimal(amount_raw.get('value', '0'))
        currency = amount_raw.get('currency', 'UNKNOWN')
        issuer = amount_raw.get('issuer', '')
    else:
        amount = Decimal(0)
        currency = 'XRP'
        issuer = None
    
    # Fee (always in drops)
    fee_drops = tx.get('Fee', '0')
    fee = drops_to_xrp(fee_drops)
    
    # Transaction result
    result = meta.get('TransactionResult', 'unknown')
    success = result == 'tesSUCCESS'
    
    return {
        'tx_hash': tx_hash,
        'ledger_index': ledger,
        'timestamp': timestamp,
        'tx_type': tx_type,
        'sender': sender,
        'destination': destination,
        'is_outgoing': is_outgoing,
        'amount': amount,
        'currency': currency,
        'issuer': issuer,
        'fee': fee,
        'success': success,
        'raw_json': str(tx_data)[:10000]
    }


def index_xrp_account(address: str, force: bool = False) -> int:
    """
    Index all transactions for an XRP account.
    Returns: total transactions indexed
    """
    indexer = XRPIndexer()
    wallet_id = get_xrp_wallet_id(address)
    
    # Get starting ledger for incremental sync
    start_ledger = 0 if force else get_last_xrp_ledger(wallet_id)
    
    print(f"{address}: Starting from ledger {start_ledger}")
    
    try:
        # Check balance first
        account_info = indexer.get_account_info(address)
        balance_drops = account_info.get('Balance', '0')
        balance = drops_to_xrp(balance_drops)
        print(f"  Current balance: {balance:.6f} XRP")
        
        # Fetch transactions
        print("  Fetching transactions...")
        txs = indexer.get_all_transactions(address, start_ledger)
        print(f"  Found {len(txs)} transactions")
        
        if not txs:
            print(f"{address}: No new transactions")
            return 0
        
        conn = get_connection()
        total_indexed = 0
        max_ledger = start_ledger
        
        for tx_data in txs:
            parsed = parse_xrp_transaction(tx_data, address)
            max_ledger = max(max_ledger, parsed['ledger_index'])
            
            try:
                conn.execute("""
                    INSERT INTO xrp_transactions 
                    (tx_hash, wallet_id, ledger_index, block_timestamp,
                     tx_type, sender, destination, is_outgoing,
                     amount, currency, issuer, fee, success, raw_json)
                    VALUES (%s, %s, %s, to_timestamp(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tx_hash) DO NOTHING
                """, (
                    parsed['tx_hash'],
                    wallet_id,
                    parsed['ledger_index'],
                    parsed['timestamp'],
                    parsed['tx_type'],
                    parsed['sender'],
                    parsed['destination'],
                    parsed['is_outgoing'],
                    str(parsed['amount']),
                    parsed['currency'],
                    parsed['issuer'],
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
        if max_ledger > start_ledger:
            update_xrp_progress(wallet_id, max_ledger, total_indexed)
        
        print(f"{address}: Complete! {total_indexed} transactions indexed")
        return total_indexed
        
    except Exception as e:
        print(f"{address}: Error - {e}")
        raise


def ensure_xrp_tables():
    """Create XRP-specific tables if they don't exist."""
    conn = get_connection()
    
    # XRP wallets table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS xrp_wallets (
            id SERIAL PRIMARY KEY,
            address VARCHAR(100) UNIQUE NOT NULL,
            label VARCHAR(255),
            is_owned BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # XRP transactions table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS xrp_transactions (
            id SERIAL PRIMARY KEY,
            tx_hash VARCHAR(128) UNIQUE NOT NULL,
            wallet_id INTEGER REFERENCES xrp_wallets(id),
            ledger_index BIGINT,
            block_timestamp TIMESTAMP,
            tx_type VARCHAR(50),
            sender VARCHAR(100),
            destination VARCHAR(100),
            is_outgoing BOOLEAN,
            amount DECIMAL(30, 10),
            currency VARCHAR(20),
            issuer VARCHAR(100),
            fee DECIMAL(20, 10),
            success BOOLEAN,
            raw_json TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Indexing progress table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS xrp_indexing_progress (
            wallet_id INTEGER PRIMARY KEY REFERENCES xrp_wallets(id),
            last_ledger BIGINT DEFAULT 0,
            total_fetched INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'pending',
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    conn.commit()
    conn.close()
    print("XRP tables ensured")


def sync_all_xrp_wallets(force: bool = False) -> int:
    """Sync all XRP wallets in the database."""
    conn = get_connection()
    wallets = conn.execute(
        "SELECT address FROM xrp_wallets WHERE is_owned = TRUE ORDER BY address"
    ).fetchall()
    conn.close()
    
    print(f"Syncing {len(wallets)} XRP wallets...")
    total = 0
    
    for (address,) in wallets:
        try:
            count = index_xrp_account(address, force)
            total += count
        except Exception as e:
            print(f"  Error syncing {address}: {e}")
    
    print(f"\n=== Total: {total} XRP transactions indexed ===")
    return total


if __name__ == "__main__":
    import sys
    
    # Ensure tables exist
    ensure_xrp_tables()
    
    if len(sys.argv) == 1 or sys.argv[1] == '--all':
        # Sync all wallets
        force = '--force' in sys.argv
        sync_all_xrp_wallets(force=force)
    elif len(sys.argv) >= 2 and sys.argv[1] != '--all':
        address = sys.argv[1]
        force = '--force' in sys.argv
        
        try:
            count = index_xrp_account(address, force=force)
            print(f"\nIndexed {count} transactions")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print("Usage:")
        print("  python xrp_indexer.py --all [--force]     # Sync all wallets")
        print("  python xrp_indexer.py <address> [--force]  # Sync specific address")
        sys.exit(1)
