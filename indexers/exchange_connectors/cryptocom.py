#!/usr/bin/env python3
"""
Crypto.com Exchange API Connector

API Docs: https://exchange-docs.crypto.com/exchange/v1/rest-ws/index.html

Note: Crypto.com has separate App and Exchange APIs.
This uses the Exchange API for trading history.
"""

import time
import hmac
import hashlib
import json
import requests
from typing import Optional, Dict, List
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection


class CryptoComConnector:
    """
    Crypto.com Exchange API connector.

    Supports:
    - Account balances
    - Trade history
    - Deposit/Withdrawal history
    """

    BASE_URL = "https://api.crypto.com/exchange/v1"

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.request_count = 0

    def _sign_request(self, method: str, params: Dict) -> str:
        """Generate HMAC-SHA256 signature."""
        params_str = ""
        if params:
            # Sort params alphabetically
            sorted_params = sorted(params.items())
            params_str = ''.join(f"{k}{v}" for k, v in sorted_params)

        nonce = str(int(time.time() * 1000))
        payload = method + str(params.get('id', '')) + self.api_key + params_str + nonce

        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature, nonce

    def _request(self, method: str, params: Optional[Dict] = None) -> Dict:
        """Make authenticated API request."""
        self.request_count += 1

        request_id = int(time.time() * 1000)
        if params is None:
            params = {}
        params['id'] = request_id

        signature, nonce = self._sign_request(method, params)

        body = {
            "id": request_id,
            "method": method,
            "api_key": self.api_key,
            "sig": signature,
            "nonce": nonce,
            "params": params
        }

        try:
            response = requests.post(
                f"{self.BASE_URL}/{method}",
                json=body,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            if data.get('code') != 0:
                raise Exception(f"API error: {data.get('message', 'Unknown error')}")

            return data.get('result', {})
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print("  Rate limited, waiting 60s...")
                time.sleep(60)
                return self._request(method, params)
            raise

    def get_accounts(self) -> List[Dict]:
        """Get account balances."""
        result = self._request('private/get-account-summary')
        return result.get('accounts', [])

    def get_trades(self, instrument_name: Optional[str] = None, start_time: Optional[int] = None) -> List[Dict]:
        """Get trade history."""
        params = {}
        if instrument_name:
            params['instrument_name'] = instrument_name
        if start_time:
            params['start_time'] = start_time

        result = self._request('private/get-trades', params)
        return result.get('trade_list', [])

    def get_deposits(self) -> List[Dict]:
        """Get deposit history."""
        result = self._request('private/get-deposit-history')
        return result.get('deposit_list', [])

    def get_withdrawals(self) -> List[Dict]:
        """Get withdrawal history."""
        result = self._request('private/get-withdrawal-history')
        return result.get('withdrawal_list', [])


def index_cryptocom_account(user_id: int, api_key: str, api_secret: str) -> int:
    """
    Index all Crypto.com transactions for a user.

    Returns: total transactions indexed
    """
    connector = CryptoComConnector(api_key, api_secret)
    total_indexed = 0

    print("Fetching Crypto.com accounts...")
    accounts = connector.get_accounts()
    print(f"Found {len(accounts)} accounts")

    conn = get_connection()

    # Create master wallet for Crypto.com
    wallet_row = conn.execute("""
        SELECT id FROM wallets WHERE account_id = ? AND chain = 'Crypto.com'
    """, (f"cryptocom:{user_id}",)).fetchone()

    if not wallet_row:
        conn.execute("""
            INSERT INTO wallets (account_id, chain, label, user_id, sync_status)
            VALUES (?, 'Crypto.com', 'Crypto.com Exchange', ?, 'in_progress')
        """, (f"cryptocom:{user_id}", user_id))
        conn.commit()
        wallet_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    else:
        wallet_id = wallet_row[0]
        conn.execute("UPDATE wallets SET sync_status = 'in_progress' WHERE id = ?", (wallet_id,))
        conn.commit()

    try:
        # Get trades
        print("  Fetching trades...")
        trades = connector.get_trades()
        print(f"  Found {len(trades)} trades")

        for trade in trades:
            side = trade.get('side', 'unknown')
            direction = 'in' if side == 'BUY' else 'out'

            try:
                conn.execute("""
                    INSERT OR IGNORE INTO transactions
                    (tx_hash, wallet_id, direction, counterparty, action_type, method_name,
                     amount, fee, block_timestamp, success, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade.get('trade_id'),
                    wallet_id,
                    direction,
                    'Crypto.com Exchange',
                    'trade',
                    trade.get('instrument_name', 'UNKNOWN'),
                    str(trade.get('traded_quantity', 0)),
                    str(trade.get('fee', 0)),
                    str(trade.get('create_time', '')),
                    True,
                    json.dumps(trade)[:10000]
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting trade: {e}")

        # Get deposits
        print("  Fetching deposits...")
        deposits = connector.get_deposits()
        print(f"  Found {len(deposits)} deposits")

        for deposit in deposits:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO transactions
                    (tx_hash, wallet_id, direction, counterparty, action_type, method_name,
                     amount, fee, block_timestamp, success, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    deposit.get('id'),
                    wallet_id,
                    'in',
                    deposit.get('address', 'External'),
                    'deposit',
                    deposit.get('currency', 'UNKNOWN'),
                    str(deposit.get('amount', 0)),
                    str(deposit.get('fee', 0)),
                    str(deposit.get('create_time', '')),
                    deposit.get('status') == 'COMPLETED',
                    json.dumps(deposit)[:10000]
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting deposit: {e}")

        # Get withdrawals
        print("  Fetching withdrawals...")
        withdrawals = connector.get_withdrawals()
        print(f"  Found {len(withdrawals)} withdrawals")

        for withdrawal in withdrawals:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO transactions
                    (tx_hash, wallet_id, direction, counterparty, action_type, method_name,
                     amount, fee, block_timestamp, success, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    withdrawal.get('id'),
                    wallet_id,
                    'out',
                    withdrawal.get('address', 'External'),
                    'withdrawal',
                    withdrawal.get('currency', 'UNKNOWN'),
                    str(withdrawal.get('amount', 0)),
                    str(withdrawal.get('fee', 0)),
                    str(withdrawal.get('create_time', '')),
                    withdrawal.get('status') == 'COMPLETED',
                    json.dumps(withdrawal)[:10000]
                ))
                total_indexed += 1
            except Exception as e:
                print(f"    Warning: Error inserting withdrawal: {e}")

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
    print(f"Crypto.com sync complete: {total_indexed} transactions indexed")
    return total_indexed


if __name__ == "__main__":
    import os

    api_key = os.environ.get('CRYPTOCOM_API_KEY')
    api_secret = os.environ.get('CRYPTOCOM_API_SECRET')

    if not api_key or not api_secret:
        print("Set CRYPTOCOM_API_KEY and CRYPTOCOM_API_SECRET environment variables")
        sys.exit(1)

    count = index_cryptocom_account(1, api_key, api_secret)
    print(f"Indexed {count} transactions")
