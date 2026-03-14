#!/usr/bin/env python3
"""
Crypto.com Exchange Indexer for NearTax
Uses Crypto.com Exchange API with HMAC authentication
"""

import os
import sys
import json
import sqlite3
import time
import hmac
import hashlib
import requests
from typing import List

# API Configuration
API_KEY = os.environ.get('CRYPTOCOM_API_KEY', '')
API_SECRET = os.environ.get('CRYPTOCOM_API_SECRET', '')
API_BASE = "https://api.crypto.com/exchange/v1"

DB_PATH = os.environ.get('NEARTAX_DB', '/home/deploy/neartax/neartax.db')
CREDS_PATH = '/home/deploy/neartax/.credentials/cryptocom.json'

def load_credentials():
    """Load API credentials from file."""
    global API_KEY, API_SECRET
    try:
        with open(CREDS_PATH, 'r') as f:
            creds = json.load(f)
            API_KEY = creds.get('api_key', API_KEY)
            API_SECRET = creds.get('api_secret', API_SECRET)
    except Exception:
        pass

def sign_request(method: str, request_id: int, params: dict = None) -> dict:
    """Sign a request for Crypto.com Exchange API."""
    nonce = int(time.time() * 1000)

    request_body = {
        "id": request_id,
        "method": method,
        "api_key": API_KEY,
        "params": params or {},
        "nonce": nonce
    }

    # Create signature
    param_string = ""
    if params:
        for key in sorted(params.keys()):
            param_string += key + str(params[key])

    sig_payload = method + str(request_id) + API_KEY + param_string + str(nonce)
    signature = hmac.new(
        API_SECRET.encode('utf-8'),
        sig_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    request_body["sig"] = signature
    return request_body

def api_request(method: str, params: dict = None) -> dict:
    """Make authenticated API request."""
    request_id = int(time.time() * 1000)
    body = sign_request(method, request_id, params)

    response = requests.post(
        f"{API_BASE}/{method}",
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=30
    )

    data = response.json()
    if data.get("code") != 0:
        print(f"API Error: {data}")

    return data

def get_account_summary() -> dict:
    """Get account balances."""
    return api_request("private/user-balance")

def get_trades(start_time: int = None, end_time: int = None) -> List[dict]:
    """Get trade history."""
    params = {}
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time

    return api_request("private/get-trades", params)

def get_transactions(start_time: int = None, end_time: int = None) -> List[dict]:
    """Get deposit/withdrawal history."""
    all_txs = []

    # Get deposits
    params = {"transaction_type": "DEPOSIT"}
    if start_time:
        params["start_time"] = start_time
    deposits = api_request("private/get-transactions", params)
    all_txs.extend(deposits.get("result", {}).get("data", []))

    # Get withdrawals
    params["transaction_type"] = "WITHDRAWAL"
    withdrawals = api_request("private/get-transactions", params)
    all_txs.extend(withdrawals.get("result", {}).get("data", []))

    return all_txs

def map_transaction_type(tx_type: str) -> str:
    """Map Crypto.com transaction type to our categories."""
    type_map = {
        "DEPOSIT": "transfer_in",
        "WITHDRAWAL": "transfer_out",
        "BUY": "buy",
        "SELL": "sell",
        "TRADING_FEE": "fee",
        "INTEREST": "interest",
        "STAKING_REWARD": "staking_reward",
        "REFERRAL": "reward",
        "AIRDROP": "airdrop",
    }
    return type_map.get(tx_type.upper(), "unknown")

def sync_transactions(user_id: int):
    """Sync all Crypto.com transactions for a user."""
    load_credentials()

    if not API_KEY or not API_SECRET:
        print("ERROR: Crypto.com API credentials not set")
        return

    print("Fetching Crypto.com account info...")

    # Test connection with account summary
    summary = get_account_summary()
    if summary.get("code") != 0:
        print(f"Connection failed: {summary}")
        return

    balances = summary.get("result", {}).get("data", [])
    print(f"Found {len(balances)} assets in account")

    for bal in balances[:5]:
        currency = bal.get("currency", "")
        available = bal.get("available", 0)
        if float(available) > 0:
            print(f"  {currency}: {available}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create import batch
    cursor.execute("""
        INSERT INTO import_batches (user_id, filename, exchange, row_count)
        VALUES (?, 'Crypto.com API Sync', 'crypto.com', 0)
    """, (user_id,))
    batch_id = cursor.lastrowid

    # Get trades
    print("\nFetching trade history...")
    trades_data = get_trades()
    trades = trades_data.get("result", {}).get("data", [])
    print(f"Found {len(trades)} trades")

    inserted = 0
    skipped = 0

    for trade in trades:
        trade_id = trade.get("trade_id", "")
        instrument = trade.get("instrument_name", "")  # e.g., "BTC_USDT"
        side = trade.get("side", "")  # BUY or SELL
        quantity = float(trade.get("traded_quantity", 0))
        price = float(trade.get("traded_price", 0))
        fee = float(trade.get("fee", 0))
        fee_currency = trade.get("fee_currency", "")
        timestamp = trade.get("create_time", 0)

        # Parse instrument
        parts = instrument.split("_")
        base_currency = parts[0] if len(parts) > 0 else ""
        quote_currency = parts[1] if len(parts) > 1 else "USDT"

        tx_type = "buy" if side == "BUY" else "sell"

        # Create hash for deduplication
        hash_input = f"{timestamp}|{instrument}|{quantity}|{side}|{trade_id}"
        tx_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:32]

        try:
            cursor.execute("""
                INSERT OR IGNORE INTO manual_transactions
                (user_id, import_batch_id, timestamp, tx_type, asset, amount,
                 quote_asset, quote_amount, price_per_unit, fee_amount, fee_asset,
                 exchange, tx_id, description, hash)
                VALUES (?, ?, datetime(?, 'unixepoch'), ?, ?, ?, ?, ?, ?, ?, ?, 'crypto.com', ?, ?, ?)
            """, (
                user_id, batch_id, timestamp // 1000, tx_type, base_currency,
                quantity, quote_currency, quantity * price, price, fee, fee_currency,
                trade_id, f"{side} {instrument}", tx_hash
            ))

            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  Insert error: {e}")
            skipped += 1

    # Get deposits/withdrawals
    print("\nFetching deposit/withdrawal history...")
    transactions = get_transactions()
    print(f"Found {len(transactions)} deposits/withdrawals")

    for tx in transactions:
        tx_id = tx.get("id", "")
        tx_type_raw = tx.get("transaction_type", "")
        currency = tx.get("currency", "")
        amount = float(tx.get("amount", 0))
        fee = float(tx.get("fee", 0))
        status = tx.get("status", "")
        timestamp = tx.get("create_time", 0)

        if status != "COMPLETED":
            continue

        tx_type = map_transaction_type(tx_type_raw)

        hash_input = f"{timestamp}|{currency}|{amount}|{tx_type_raw}|{tx_id}"
        tx_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:32]

        try:
            cursor.execute("""
                INSERT OR IGNORE INTO manual_transactions
                (user_id, import_batch_id, timestamp, tx_type, asset, amount,
                 fee_amount, fee_asset, exchange, tx_id, description, hash)
                VALUES (?, ?, datetime(?, 'unixepoch'), ?, ?, ?, ?, ?, 'crypto.com', ?, ?, ?)
            """, (
                user_id, batch_id, timestamp // 1000, tx_type, currency,
                amount, fee, currency, tx_id, tx_type_raw, tx_hash
            ))

            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  Insert error: {e}")
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
    """, (len(trades) + len(transactions), inserted, skipped, batch_id))

    conn.commit()
    conn.close()

    print(f"\nDone! Inserted: {inserted}, Skipped: {skipped}")
    return {"inserted": inserted, "skipped": skipped}

def test_connection():
    """Test API connection."""
    load_credentials()

    if not API_KEY or not API_SECRET:
        print("ERROR: API credentials not configured")
        print(f"  API_KEY: {'set' if API_KEY else 'missing'}")
        print(f"  API_SECRET: {'set' if API_SECRET else 'missing'}")
        return False

    print("Testing Crypto.com Exchange API connection...")
    print(f"  API Key: {API_KEY[:8]}...")

    result = get_account_summary()

    if result.get("code") == 0:
        balances = result.get("result", {}).get("data", [])
        print(f"✓ Connected! Found {len(balances)} assets")

        non_zero = [b for b in balances if float(b.get("available", 0)) > 0]
        for bal in non_zero[:5]:
            print(f"  {bal.get('currency')}: {bal.get('available')}")
        return True
    else:
        print(f"✗ Connection failed: {result}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            test_connection()
        elif sys.argv[1] == "sync" and len(sys.argv) > 2:
            user_id = int(sys.argv[2])
            sync_transactions(user_id)
        else:
            print("Usage:")
            print("  python3 cryptocom_indexer.py test")
            print("  python3 cryptocom_indexer.py sync <user_id>")
    else:
        print("Crypto.com Exchange Indexer for NearTax")
        print("Run with 'test' to verify connection")
