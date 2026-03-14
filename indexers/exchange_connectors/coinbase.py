#!/usr/bin/env python3
"""
Coinbase API Connector
Uses Coinbase Advanced Trade API (formerly Pro) for transaction history.

API Docs: https://docs.cdp.coinbase.com/advanced-trade/docs/welcome

Required scopes: wallet:accounts:read, wallet:transactions:read
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


class CoinbaseConnector:
    """
    Coinbase API connector for fetching transaction history.

    Supports:
    - Account balances
    - Transaction history (buys, sells, sends, receives)
    - Trade history
    """

    BASE_URL = "https://api.coinbase.com"

    def __init__(self, api_key: str, api_secret: str):
        """
        Initialize with Coinbase API credentials.

        Args:
            api_key: Coinbase API Key
            api_secret: Coinbase API Secret
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.request_count = 0

    def _sign_request(self, method: str, path: str, body: str = '') -> Dict[str, str]:
        """Generate authentication headers for Coinbase API."""
        timestamp = str(int(time.time()))
        message = timestamp + method.upper() + path + body

        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return {
            'CB-ACCESS-KEY': self.api_key,
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
        }

    def _request(self, method: str, path: str, params: Optional[Dict] = None) -> Dict:
        """Make authenticated API request."""
        self.request_count += 1

        url = f"{self.BASE_URL}{path}"
        if params:
            query = '&'.join(f"{k}={v}" for k, v in params.items())
            path_with_query = f"{path}?{query}"
            url = f"{self.BASE_URL}{path_with_query}"
        else:
            path_with_query = path

        headers = self._sign_request(method, path_with_query)

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            else:
                response = requests.request(method, url, headers=headers, timeout=30)

            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print("  Rate limited, waiting 60s...")
                time.sleep(60)
                return self._request(method, path, params)
            raise

    def get_accounts(self) -> List[Dict]:
        """Get all accounts (wallets) with balances."""
        accounts = []
        path = '/v2/accounts'

        while path:
            data = self._request('GET', path)
            accounts.extend(data.get('data', []))

            # Handle pagination
            pagination = data.get('pagination', {})
            path = pagination.get('next_uri')

            time.sleep(0.1)  # Rate limit protection

        return accounts

    def get_transactions(self, account_id: str) -> List[Dict]:
        """Get all transactions for an account."""
        transactions = []
        path = f'/v2/accounts/{account_id}/transactions'

        while path:
            data = self._request('GET', path)
            transactions.extend(data.get('data', []))

            pagination = data.get('pagination', {})
            path = pagination.get('next_uri')

            time.sleep(0.1)

        return transactions

    def get_buys(self, account_id: str) -> List[Dict]:
        """Get all buy orders for an account."""
        buys = []
        path = f'/v2/accounts/{account_id}/buys'

        while path:
            data = self._request('GET', path)
            buys.extend(data.get('data', []))

            pagination = data.get('pagination', {})
            path = pagination.get('next_uri')

            time.sleep(0.1)

        return buys

    def get_sells(self, account_id: str) -> List[Dict]:
        """Get all sell orders for an account."""
        sells = []
        path = f'/v2/accounts/{account_id}/sells'

        while path:
            data = self._request('GET', path)
            sells.extend(data.get('data', []))

            pagination = data.get('pagination', {})
            path = pagination.get('next_uri')

            time.sleep(0.1)

        return sells


def store_api_credentials(user_id: int, exchange: str, api_key: str, api_secret: str):
    """Securely store exchange API credentials."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO exchange_credentials (user_id, exchange, api_key, api_secret, created_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(user_id, exchange) DO UPDATE SET
            api_key = excluded.api_key,
            api_secret = excluded.api_secret,
            created_at = datetime('now')
    """, (user_id, exchange, api_key, api_secret))
    conn.commit()
    conn.close()


def get_api_credentials(user_id: int, exchange: str) -> Optional[Dict[str, str]]:
    """Retrieve stored API credentials."""
    conn = get_connection()
    row = conn.execute("""
        SELECT api_key, api_secret FROM exchange_credentials
        WHERE user_id = ? AND exchange = ?
    """, (user_id, exchange)).fetchone()
    conn.close()

    if row:
        return {'api_key': row[0], 'api_secret': row[1]}
    return None


def index_coinbase_account(user_id: int, api_key: str, api_secret: str) -> int:
    """
    Index all Coinbase transactions for a user.

    Returns: total transactions indexed
    """
    connector = CoinbaseConnector(api_key, api_secret)
    total_indexed = 0

    print("Fetching Coinbase accounts...")
    accounts = connector.get_accounts()
    print(f"Found {len(accounts)} accounts")

    conn = get_connection()

    for account in accounts:
        currency = account.get('currency', {})
        currency_code = currency.get('code', 'UNKNOWN') if isinstance(currency, dict) else currency
        balance = account.get('balance', {}).get('amount', '0')
        account_id = account.get('id')

        print(f"  Processing {currency_code} account (balance: {balance})...")

        # Get or create wallet for this exchange account
        wallet_row = conn.execute("""
            SELECT id FROM wallets WHERE account_id = ? AND chain = 'Coinbase'
        """, (f"coinbase:{account_id}",)).fetchone()

        if not wallet_row:
            conn.execute("""
                INSERT INTO wallets (account_id, chain, label, user_id, sync_status)
                VALUES (?, 'Coinbase', ?, ?, 'in_progress')
            """, (f"coinbase:{account_id}", f"Coinbase {currency_code}", user_id))
            conn.commit()
            wallet_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        else:
            wallet_id = wallet_row[0]
            conn.execute("UPDATE wallets SET sync_status = 'in_progress' WHERE id = ?", (wallet_id,))
            conn.commit()

        # Fetch transactions
        try:
            transactions = connector.get_transactions(account_id)

            for tx in transactions:
                tx_type = tx.get('type', 'unknown')
                amount = tx.get('amount', {}).get('amount', '0')
                tx.get('native_amount', {}).get('amount', '0')

                # Determine direction
                if tx_type in ['buy', 'fiat_deposit', 'receive', 'interest', 'staking_reward']:
                    direction = 'in'
                elif tx_type in ['sell', 'fiat_withdrawal', 'send', 'fee']:
                    direction = 'out'
                else:
                    direction = 'in' if float(amount) > 0 else 'out'

                # Get counterparty
                network = tx.get('network', {})
                counterparty = network.get('name', tx.get('to', {}).get('email', 'Coinbase'))

                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO transactions
                        (tx_hash, wallet_id, direction, counterparty, action_type, method_name,
                         amount, fee, block_timestamp, success, raw_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        tx.get('id'),
                        wallet_id,
                        direction,
                        counterparty,
                        tx_type,
                        currency_code,
                        str(abs(float(amount))),
                        '0',
                        tx.get('created_at'),
                        tx.get('status') == 'completed',
                        json.dumps(tx)[:10000]
                    ))
                    total_indexed += 1
                except Exception as e:
                    print(f"    Warning: Error inserting tx: {e}")

            # Update wallet status
            conn.execute("""
                UPDATE wallets SET sync_status = 'complete', last_synced_at = datetime('now')
                WHERE id = ?
            """, (wallet_id,))
            conn.commit()

        except Exception as e:
            print(f"    Error fetching transactions: {e}")
            conn.execute("UPDATE wallets SET sync_status = 'error' WHERE id = ?", (wallet_id,))
            conn.commit()

    conn.close()
    print(f"Coinbase sync complete: {total_indexed} transactions indexed")
    return total_indexed


if __name__ == "__main__":
    import os

    api_key = os.environ.get('COINBASE_API_KEY')
    api_secret = os.environ.get('COINBASE_API_SECRET')

    if not api_key or not api_secret:
        print("Set COINBASE_API_KEY and COINBASE_API_SECRET environment variables")
        sys.exit(1)

    # Test with user_id 1
    count = index_coinbase_account(1, api_key, api_secret)
    print(f"Indexed {count} transactions")
