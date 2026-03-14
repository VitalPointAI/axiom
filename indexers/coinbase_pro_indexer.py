#!/usr/bin/env python3
# DEPRECATED: Use indexers/exchange_parsers/coinbase.py instead.
"""
Coinbase Advanced Trade API Indexer for NearTax
Fetches transaction history from Coinbase Pro / Advanced Trade API
"""

import os
import hmac
import hashlib
import time
import json
import warnings
import requests
from datetime import datetime
import psycopg2

warnings.warn(
    "coinbase_pro_indexer.py is deprecated. "
    "Use indexers/exchange_parsers/coinbase.py for Coinbase CSV imports. "
    "Will be removed in v2.",
    DeprecationWarning,
    stacklevel=2,
)

# Database connection — hardcoded fallback kept for backward compat; prefer DATABASE_URL env var
DB_URL = os.environ.get("DATABASE_URL", "postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax")

# Coinbase API base URLs
COINBASE_API_URL = "https://api.coinbase.com/api/v3/brokerage"
COINBASE_PRO_API_URL = "https://api.pro.coinbase.com"  # Legacy

def get_db_connection():
    return psycopg2.connect(DB_URL)

def sign_coinbase_request(api_secret: str, timestamp: str, method: str, path: str, body: str = "") -> str:
    """Sign request for Coinbase Advanced Trade API"""
    message = f"{timestamp}{method}{path}{body}"
    signature = hmac.new(
        api_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def fetch_coinbase_accounts(api_key: str, api_secret: str) -> list:
    """Fetch all accounts from Coinbase"""
    timestamp = str(int(time.time()))
    path = "/accounts"

    signature = sign_coinbase_request(api_secret, timestamp, "GET", path)

    headers = {
        "CB-ACCESS-KEY": api_key,
        "CB-ACCESS-SIGN": signature,
        "CB-ACCESS-TIMESTAMP": timestamp,
        "Content-Type": "application/json"
    }

    response = requests.get(f"{COINBASE_API_URL}{path}", headers=headers)

    if response.status_code != 200:
        print(f"Error fetching accounts: {response.status_code} - {response.text}")
        return []

    data = response.json()
    return data.get("accounts", [])

def fetch_coinbase_transactions(api_key: str, api_secret: str, account_id: str, cursor: str = None) -> dict:
    """Fetch transactions for an account"""
    timestamp = str(int(time.time()))
    path = f"/accounts/{account_id}/transactions"
    if cursor:
        path += f"?cursor={cursor}"

    signature = sign_coinbase_request(api_secret, timestamp, "GET", path)

    headers = {
        "CB-ACCESS-KEY": api_key,
        "CB-ACCESS-SIGN": signature,
        "CB-ACCESS-TIMESTAMP": timestamp,
        "Content-Type": "application/json"
    }

    response = requests.get(f"{COINBASE_API_URL}{path}", headers=headers)

    if response.status_code != 200:
        print(f"Error fetching transactions: {response.status_code} - {response.text}")
        return {"transactions": [], "cursor": None}

    return response.json()

def fetch_coinbase_orders(api_key: str, api_secret: str, start_date: str = None) -> list:
    """Fetch filled orders (buys/sells)"""
    timestamp = str(int(time.time()))
    path = "/orders/historical/fills"

    params = []
    if start_date:
        params.append(f"start_date={start_date}")
    if params:
        path += "?" + "&".join(params)

    signature = sign_coinbase_request(api_secret, timestamp, "GET", path)

    headers = {
        "CB-ACCESS-KEY": api_key,
        "CB-ACCESS-SIGN": signature,
        "CB-ACCESS-TIMESTAMP": timestamp,
        "Content-Type": "application/json"
    }

    response = requests.get(f"{COINBASE_API_URL}{path}", headers=headers)

    if response.status_code != 200:
        print(f"Error fetching orders: {response.status_code} - {response.text}")
        return []

    data = response.json()
    return data.get("fills", [])

def sync_coinbase_connection(conn, connection_id: int, api_key: str, api_secret: str, passphrase: str = None):
    """Sync a Coinbase Pro connection"""
    cursor = conn.cursor()

    print(f"Syncing Coinbase connection {connection_id}...")

    # Update status to syncing
    cursor.execute(
        "UPDATE exchange_connections SET status = 'syncing', last_sync_at = NOW() WHERE id = %s",
        (connection_id,)
    )
    conn.commit()

    try:
        # Get or create exchange wallet
        cursor.execute(
            """
            SELECT id FROM wallets
            WHERE account_id = %s AND chain = 'exchange'
            """,
            (f"exchange:coinbase_pro:{connection_id}",)
        )
        wallet = cursor.fetchone()

        if not wallet:
            cursor.execute(
                """
                INSERT INTO wallets (user_id, account_id, label, chain, sync_status, created_at)
                SELECT user_id, %s, 'Coinbase Pro', 'exchange', 'syncing', NOW()
                FROM exchange_connections WHERE id = %s
                RETURNING id
                """,
                (f"exchange:coinbase_pro:{connection_id}", connection_id)
            )
            wallet = cursor.fetchone()
            conn.commit()

        wallet_id = wallet[0]

        # Fetch accounts
        accounts = fetch_coinbase_accounts(api_key, api_secret)
        print(f"Found {len(accounts)} accounts")

        # Fetch orders/fills
        orders = fetch_coinbase_orders(api_key, api_secret)
        print(f"Found {len(orders)} order fills")

        # Process orders into transactions
        transactions = []
        for order in orders:
            tx_hash = f"coinbase_pro_{order.get('trade_id', order.get('order_id', ''))}"

            # Parse the product (e.g., "BTC-USD")
            product = order.get("product_id", "")
            parts = product.split("-")
            base_asset = parts[0] if parts else "UNKNOWN"
            quote_asset = parts[1] if len(parts) > 1 else "USD"

            side = order.get("side", "").upper()
            size = float(order.get("size", 0))
            price = float(order.get("price", 0))
            float(order.get("fee", 0))
            trade_time = order.get("trade_time", datetime.utcnow().isoformat())

            # Buy = receive base asset, spend quote
            # Sell = spend base asset, receive quote
            if side == "BUY":
                transactions.append({
                    "wallet_id": wallet_id,
                    "tx_hash": tx_hash,
                    "direction": "in",
                    "asset": base_asset,
                    "amount": str(size),
                    "counterparty": "coinbase_pro",
                    "action_type": "BUY",
                    "block_timestamp": int(datetime.fromisoformat(trade_time.replace("Z", "+00:00")).timestamp() * 1000),
                    "source": "coinbase_pro",
                    "exchange": "coinbase_pro",
                    "description": f"Buy {size} {base_asset} @ {price} {quote_asset}",
                    "quote_asset": quote_asset,
                    "quote_amount": str(size * price),
                    "cost_basis_cad": 0,
                })
            else:
                transactions.append({
                    "wallet_id": wallet_id,
                    "tx_hash": tx_hash,
                    "direction": "out",
                    "asset": base_asset,
                    "amount": str(size),
                    "counterparty": "coinbase_pro",
                    "action_type": "SELL",
                    "block_timestamp": int(datetime.fromisoformat(trade_time.replace("Z", "+00:00")).timestamp() * 1000),
                    "source": "coinbase_pro",
                    "exchange": "coinbase_pro",
                    "description": f"Sell {size} {base_asset} @ {price} {quote_asset}",
                    "quote_asset": quote_asset,
                    "quote_amount": str(size * price),
                    "cost_basis_cad": 0,
                })

        # Insert transactions
        if transactions:
            for tx in transactions:
                cursor.execute(
                    """
                    INSERT INTO transactions (
                        wallet_id, tx_hash, direction, asset, amount, counterparty,
                        action_type, block_timestamp, source, exchange, description,
                        quote_asset, quote_amount, cost_basis_cad, status, created_at
                    ) VALUES (
                        %(wallet_id)s, %(tx_hash)s, %(direction)s, %(asset)s, %(amount)s, %(counterparty)s,
                        %(action_type)s, %(block_timestamp)s, %(source)s, %(exchange)s, %(description)s,
                        %(quote_asset)s, %(quote_amount)s, %(cost_basis_cad)s, 'success', NOW()
                    ) ON CONFLICT (tx_hash) DO NOTHING
                    """,
                    tx
                )
            conn.commit()
            print(f"Inserted {len(transactions)} transactions")

        # Update connection status
        cursor.execute(
            """
            UPDATE exchange_connections
            SET status = 'connected', last_sync_at = NOW(), last_error = NULL
            WHERE id = %s
            """,
            (connection_id,)
        )

        # Update wallet status
        cursor.execute(
            "UPDATE wallets SET sync_status = 'complete', last_synced_at = NOW() WHERE id = %s",
            (wallet_id,)
        )
        conn.commit()

        print(f"Successfully synced Coinbase connection {connection_id}")

    except Exception as e:
        print(f"Error syncing connection {connection_id}: {e}")
        cursor.execute(
            "UPDATE exchange_connections SET status = 'error', last_error = %s WHERE id = %s",
            (str(e), connection_id)
        )
        conn.commit()

def main():
    """Main sync function - syncs all Coinbase Pro connections"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get all active Coinbase Pro connections
    cursor.execute(
        """
        SELECT id, api_key, api_secret, additional_config
        FROM exchange_connections
        WHERE exchange = 'coinbase_pro' AND status != 'disabled'
        """
    )
    connections = cursor.fetchall()

    print(f"Found {len(connections)} Coinbase Pro connections to sync")

    for conn_id, api_key, api_secret, config in connections:
        passphrase = None
        if config:
            try:
                config_data = json.loads(config) if isinstance(config, str) else config
                passphrase = config_data.get("passphrase")
            except Exception:
                pass

        sync_coinbase_connection(conn, conn_id, api_key, api_secret, passphrase)

    conn.close()
    print("Done!")

if __name__ == "__main__":
    main()
