#!/usr/bin/env python3
"""
Kraken Exchange API Connector

API Docs: https://docs.kraken.com/api/

Kraken uses base64-encoded API keys with HMAC-SHA512 signatures.
"""

import time
import hmac
import hashlib
import base64
import urllib.parse
import json
import requests
from typing import Optional, Dict, List
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection


class KrakenConnector:
    """
    Kraken Exchange API connector.
    
    Supports:
    - Account balances
    - Trade history (ledger)
    - Deposit/Withdrawal history
    """
    
    BASE_URL = "https://api.kraken.com"
    
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = base64.b64decode(api_secret)
        self.request_count = 0
    
    def _sign_request(self, path: str, data: Dict) -> str:
        """Generate HMAC-SHA512 signature."""
        postdata = urllib.parse.urlencode(data)
        encoded = (str(data['nonce']) + postdata).encode()
        message = path.encode() + hashlib.sha256(encoded).digest()
        
        signature = hmac.new(
            self.api_secret,
            message,
            hashlib.sha512
        )
        
        return base64.b64encode(signature.digest()).decode()
    
    def _request(self, method: str, params: Optional[Dict] = None, private: bool = True) -> Dict:
        """Make API request."""
        self.request_count += 1
        
        if private:
            path = f"/0/private/{method}"
            url = f"{self.BASE_URL}{path}"
            
            if params is None:
                params = {}
            params['nonce'] = int(time.time() * 1000)
            
            headers = {
                'API-Key': self.api_key,
                'API-Sign': self._sign_request(path, params),
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            response = requests.post(url, data=params, headers=headers, timeout=30)
        else:
            path = f"/0/public/{method}"
            url = f"{self.BASE_URL}{path}"
            response = requests.get(url, params=params, timeout=30)
        
        response.raise_for_status()
        data = response.json()
        
        if data.get('error'):
            errors = data['error']
            if any('Rate limit' in str(e) for e in errors):
                print("  Rate limited, waiting 60s...")
                time.sleep(60)
                return self._request(method, params, private)
            raise Exception(f"API error: {errors}")
        
        return data.get('result', {})
    
    def get_balance(self) -> Dict[str, str]:
        """Get account balances."""
        return self._request('Balance')
    
    def get_trade_balance(self, asset: str = 'ZUSD') -> Dict:
        """Get trade balance summary."""
        return self._request('TradeBalance', {'asset': asset})
    
    def get_ledger(self, asset: Optional[str] = None, type_: Optional[str] = None, 
                   start: Optional[int] = None, end: Optional[int] = None,
                   offset: int = 0) -> Dict:
        """
        Get ledger entries (all account activity).
        
        Types: all, deposit, withdrawal, trade, margin, rollover, credit, transfer, settled, staking, sale
        """
        params = {'ofs': offset}
        if asset:
            params['asset'] = asset
        if type_:
            params['type'] = type_
        if start:
            params['start'] = start
        if end:
            params['end'] = end
        
        return self._request('Ledgers', params)
    
    def get_trades_history(self, start: Optional[int] = None, end: Optional[int] = None,
                           offset: int = 0) -> Dict:
        """Get closed trades history."""
        params = {'ofs': offset}
        if start:
            params['start'] = start
        if end:
            params['end'] = end
        
        return self._request('TradesHistory', params)
    
    def get_deposits(self, asset: Optional[str] = None) -> List[Dict]:
        """Get deposit history."""
        params = {}
        if asset:
            params['asset'] = asset
        return self._request('DepositStatus', params)
    
    def get_withdrawals(self, asset: Optional[str] = None) -> List[Dict]:
        """Get withdrawal history."""
        params = {}
        if asset:
            params['asset'] = asset
        return self._request('WithdrawStatus', params)


def index_kraken_account(user_id: int, api_key: str, api_secret: str) -> int:
    """
    Index all Kraken transactions for a user.
    
    Returns: total transactions indexed
    """
    connector = KrakenConnector(api_key, api_secret)
    total_indexed = 0
    
    print("Fetching Kraken balance...")
    balances = connector.get_balance()
    print(f"Found {len(balances)} assets with balance")
    
    conn = get_connection()
    
    # Create master wallet for Kraken
    wallet_row = conn.execute("""
        SELECT id FROM wallets WHERE account_id = ? AND chain = 'Kraken'
    """, (f"kraken:{user_id}",)).fetchone()
    
    if not wallet_row:
        conn.execute("""
            INSERT INTO wallets (account_id, chain, label, user_id, sync_status)
            VALUES (?, 'Kraken', 'Kraken Exchange', ?, 'in_progress')
        """, (f"kraken:{user_id}", user_id))
        conn.commit()
        wallet_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    else:
        wallet_id = wallet_row[0]
        conn.execute("UPDATE wallets SET sync_status = 'in_progress' WHERE id = ?", (wallet_id,))
        conn.commit()
    
    try:
        # Get full ledger (all account activity)
        print("  Fetching ledger entries...")
        offset = 0
        all_ledger = []
        
        while True:
            result = connector.get_ledger(offset=offset)
            ledger = result.get('ledger', {})
            
            if not ledger:
                break
            
            all_ledger.extend(ledger.values())
            
            count = result.get('count', 0)
            offset += len(ledger)
            
            if offset >= count:
                break
            
            time.sleep(0.5)  # Rate limit protection
        
        print(f"  Found {len(all_ledger)} ledger entries")
        
        for entry in all_ledger:
            entry_type = entry.get('type', 'unknown')
            amount = float(entry.get('amount', 0))
            direction = 'in' if amount > 0 else 'out'
            
            # Map Kraken types
            action_type = {
                'deposit': 'deposit',
                'withdrawal': 'withdrawal',
                'trade': 'trade',
                'margin': 'margin',
                'rollover': 'rollover',
                'credit': 'credit',
                'transfer': 'transfer',
                'settled': 'settled',
                'staking': 'staking_reward',
                'sale': 'sale',
            }.get(entry_type, entry_type)
            
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO transactions 
                    (tx_hash, wallet_id, direction, counterparty, action_type, method_name,
                     amount, fee, block_timestamp, success, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry.get('refid'),
                    wallet_id,
                    direction,
                    'Kraken Exchange',
                    action_type,
                    entry.get('asset', 'UNKNOWN'),
                    str(abs(amount)),
                    str(abs(float(entry.get('fee', 0)))),
                    str(entry.get('time', '')),
                    True,
                    json.dumps(entry)[:10000]
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting entry: {e}")
        
        conn.execute("""
            UPDATE wallets SET sync_status = 'complete', last_synced_at = datetime('now')
            WHERE id = ?
        """, (wallet_id,))
        conn.commit()
        
    except Exception as e:
        print(f"Error: {e}")
        conn.execute("UPDATE wallets SET sync_status = 'error' WHERE id = ?", (wallet_id,))
        conn.commit()
        raise
    
    conn.close()
    print(f"Kraken sync complete: {total_indexed} transactions indexed")
    return total_indexed


if __name__ == "__main__":
    import os
    
    api_key = os.environ.get('KRAKEN_API_KEY')
    api_secret = os.environ.get('KRAKEN_API_SECRET')
    
    if not api_key or not api_secret:
        print("Set KRAKEN_API_KEY and KRAKEN_API_SECRET environment variables")
        sys.exit(1)
    
    count = index_kraken_account(1, api_key, api_secret)
    print(f"Indexed {count} transactions")
