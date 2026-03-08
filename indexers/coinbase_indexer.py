#!/usr/bin/env python3
"""
Coinbase Indexer for NearTax
Uses Coinbase Advanced Trade API with JWT authentication
"""

import os
import sys
import json
import sqlite3
import time
import secrets
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# Try to import JWT libraries
try:
    import jwt
    from cryptography.hazmat.primitives import serialization
    HAS_JWT = True
except ImportError:
    HAS_JWT = False
    print("Warning: PyJWT and cryptography required. Install with:")
    print("  pip install PyJWT cryptography")

DB_PATH = os.environ.get('NEARTAX_DB', '/home/deploy/neartax/neartax.db')
CREDS_PATH = os.environ.get('COINBASE_CREDS', '/home/deploy/neartax/.credentials/coinbase.json')

# Coinbase API base URL
API_BASE = "https://api.coinbase.com"

def load_credentials():
    """Load Coinbase API credentials."""
    with open(CREDS_PATH, 'r') as f:
        return json.load(f)

def generate_jwt(method: str, path: str) -> str:
    """Generate JWT token for Coinbase API authentication."""
    creds = load_credentials()
    
    private_key_pem = creds['private_key']
    key_name = creds['key_name']
    
    # Create JWT payload
    uri = f"{method} api.coinbase.com{path}"
    
    payload = {
        "sub": key_name,
        "iss": "cdp",
        "nbf": int(time.time()),
        "exp": int(time.time()) + 120,  # 2 minute expiry
        "uri": uri,
    }
    
    headers = {
        "kid": key_name,
        "nonce": secrets.token_hex(16),
        "typ": "JWT",
        "alg": "ES256"
    }
    
    # Load private key and sign
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(),
        password=None
    )
    
    token = jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers=headers
    )
    
    return token

def coinbase_request(method: str, path: str, params: dict = None) -> dict:
    """Make authenticated request to Coinbase API."""
    
    url = f"{API_BASE}{path}"
    token = generate_jwt(method, path)
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    if method == "GET":
        response = requests.get(url, headers=headers, params=params, timeout=30)
    else:
        response = requests.post(url, headers=headers, json=params, timeout=30)
    
    if response.status_code != 200:
        print(f"API error {response.status_code}: {response.text[:500]}")
        return {"error": response.text}
    
    return response.json()

def get_accounts() -> List[Dict]:
    """Get all Coinbase accounts (wallets)."""
    accounts = []
    cursor = None
    
    while True:
        params = {"limit": 250}
        if cursor:
            params["cursor"] = cursor
        
        data = coinbase_request("GET", "/api/v3/brokerage/accounts", params)
        
        if "error" in data:
            break
        
        accounts.extend(data.get("accounts", []))
        
        if not data.get("has_next"):
            break
        cursor = data.get("cursor")
    
    return accounts

def get_transactions(account_id: str) -> List[Dict]:
    """Get transaction history for an account."""
    transactions = []
    cursor = None
    
    while True:
        params = {"limit": 250}
        if cursor:
            params["cursor"] = cursor
        
        data = coinbase_request("GET", f"/api/v3/brokerage/accounts/{account_id}/ledger", params)
        
        if "error" in data:
            break
        
        transactions.extend(data.get("entries", []))
        
        if not data.get("has_next"):
            break
        cursor = data.get("cursor")
    
    return transactions

def get_orders(start_date: str = None) -> List[Dict]:
    """Get order (trade) history."""
    orders = []
    cursor = None
    
    while True:
        params = {
            "limit": 250,
            "order_status": ["FILLED"]
        }
        if cursor:
            params["cursor"] = cursor
        if start_date:
            params["start_date"] = start_date
        
        data = coinbase_request("GET", "/api/v3/brokerage/orders/historical/batch", params)
        
        if "error" in data:
            break
        
        orders.extend(data.get("orders", []))
        
        if not data.get("has_next"):
            break
        cursor = data.get("cursor")
    
    return orders

def map_transaction_type(cb_type: str) -> str:
    """Map Coinbase transaction type to our categories."""
    type_map = {
        "trade": "trade",
        "buy": "buy",
        "sell": "sell",
        "send": "transfer_out",
        "receive": "transfer_in",
        "deposit": "transfer_in",
        "withdrawal": "transfer_out",
        "interest": "interest",
        "staking_reward": "staking_reward",
        "inflation_reward": "staking_reward",
        "fee": "fee",
        "airdrop": "airdrop",
        "fork": "airdrop",
    }
    return type_map.get(cb_type.lower(), "unknown")

def sync_coinbase_transactions(user_id: int):
    """Sync all Coinbase transactions for a user."""
    
    if not HAS_JWT:
        print("ERROR: PyJWT and cryptography libraries required")
        return
    
    print("Fetching Coinbase accounts...")
    accounts = get_accounts()
    print(f"Found {len(accounts)} accounts")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create import batch
    cursor.execute("""
        INSERT INTO import_batches (user_id, filename, exchange, row_count)
        VALUES (?, 'Coinbase API Sync', 'coinbase', 0)
    """, (user_id,))
    batch_id = cursor.lastrowid
    
    total_transactions = 0
    inserted = 0
    skipped = 0
    
    for account in accounts:
        currency = account.get("currency", "")
        balance = float(account.get("available_balance", {}).get("value", 0))
        account_id = account.get("uuid", "")
        
        if balance == 0 and currency not in ["BTC", "ETH", "NEAR"]:
            continue  # Skip empty non-major accounts
        
        print(f"  Fetching {currency} transactions...")
        
        # Get ledger entries for this account
        transactions = get_transactions(account_id)
        total_transactions += len(transactions)
        
        for tx in transactions:
            entry_type = tx.get("entry_type", "")
            amount = float(tx.get("amount", {}).get("value", 0))
            timestamp = tx.get("created_at", "")
            tx_id = tx.get("entry_id", "")
            
            tx_type = map_transaction_type(entry_type)
            
            # Create hash for deduplication
            import hashlib
            hash_input = f"{timestamp}|{currency}|{amount}|{entry_type}|{tx_id}"
            tx_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:32]
            
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO manual_transactions 
                    (user_id, import_batch_id, timestamp, tx_type, asset, amount,
                     exchange, tx_id, description, hash)
                    VALUES (?, ?, ?, ?, ?, ?, 'coinbase', ?, ?, ?)
                """, (
                    user_id, batch_id, timestamp, tx_type, currency,
                    abs(amount), tx_id, entry_type, tx_hash
                ))
                
                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"    Error: {e}")
                skipped += 1
    
    # Also get filled orders
    print("Fetching order history...")
    orders = get_orders()
    print(f"Found {len(orders)} orders")
    
    for order in orders:
        product_id = order.get("product_id", "")  # e.g., "BTC-CAD"
        side = order.get("side", "")  # BUY or SELL
        filled_value = float(order.get("filled_value", 0))
        filled_size = float(order.get("filled_size", 0))
        created_at = order.get("created_time", "")
        order_id = order.get("order_id", "")
        
        if filled_size == 0:
            continue
        
        base_currency = product_id.split("-")[0] if "-" in product_id else product_id
        quote_currency = product_id.split("-")[1] if "-" in product_id else "CAD"
        
        tx_type = "buy" if side == "BUY" else "sell"
        
        import hashlib
        hash_input = f"{created_at}|{product_id}|{filled_size}|{side}|{order_id}"
        tx_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:32]
        
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO manual_transactions 
                (user_id, import_batch_id, timestamp, tx_type, asset, amount,
                 quote_asset, quote_amount, price_per_unit, exchange, tx_id, description, hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'coinbase', ?, ?, ?)
            """, (
                user_id, batch_id, created_at, tx_type, base_currency,
                filled_size, quote_currency, filled_value,
                filled_value / filled_size if filled_size else None,
                order_id, f"{side} {product_id}", tx_hash
            ))
            
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"    Order error: {e}")
            skipped += 1
    
    # Update batch
    cursor.execute("""
        UPDATE import_batches 
        SET status = 'completed',
            row_count = ?,
            imported_count = ?,
            skipped_count = ?,
            completed_at = datetime('now')
        WHERE id = ?
    """, (total_transactions + len(orders), inserted, skipped, batch_id))
    
    conn.commit()
    conn.close()
    
    print(f"\nDone! Inserted: {inserted}, Skipped: {skipped}")
    return {"inserted": inserted, "skipped": skipped}

def test_connection():
    """Test Coinbase API connection."""
    if not HAS_JWT:
        print("ERROR: Install required libraries:")
        print("  pip install PyJWT cryptography")
        return False
    
    print("Testing Coinbase API connection...")
    accounts = get_accounts()
    
    if accounts:
        print(f"✓ Connected! Found {len(accounts)} accounts:")
        for acc in accounts[:5]:
            currency = acc.get("currency", "?")
            balance = acc.get("available_balance", {}).get("value", "0")
            print(f"  - {currency}: {balance}")
        if len(accounts) > 5:
            print(f"  ... and {len(accounts) - 5} more")
        return True
    else:
        print("✗ Failed to fetch accounts")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            test_connection()
        elif sys.argv[1] == "sync" and len(sys.argv) > 2:
            user_id = int(sys.argv[2])
            sync_coinbase_transactions(user_id)
        else:
            print("Usage:")
            print("  python3 coinbase_indexer.py test")
            print("  python3 coinbase_indexer.py sync <user_id>")
    else:
        print("Coinbase Indexer for NearTax")
        print("Run with 'test' to verify connection")
