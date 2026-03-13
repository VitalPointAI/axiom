#!/usr/bin/env python3
"""Quick backfill for missing transactions since Feb 25, 2026."""

import sqlite3
import logging
import requests
import json
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("/home/deploy/neartax/neartax.db")
NEARBLOCKS_API = "https://api3.nearblocks.io/v1"

def get_wallet_transactions(account_id, limit=100):
    """Fetch recent transactions from NearBlocks."""
    url = f"{NEARBLOCKS_API}/account/{account_id}/txns"
    params = {"page": 1, "per_page": limit, "order": "desc"}
    
    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 200:
            data = r.json()
            return data.get("txns", [])
    except Exception as e:
        print(f"Error fetching {account_id}: {e}")
    return []

def get_receipt_details(tx_hash):
    """Get transaction receipts for amount extraction."""
    url = f"{NEARBLOCKS_API}/txns/{tx_hash}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.json().get("txns", [{}])[0]
    except (requests.RequestException, ConnectionError, TimeoutError, ValueError, KeyError) as e:
        logger.warning("Failed to fetch receipt details for tx %s: %s", tx_hash, e)
    return {}

def parse_nearblocks_tx(tx, wallet_id, account_id):
    """Parse NearBlocks transaction into our schema format."""
    tx_hash = tx.get("transaction_hash", "")
    block_ts = int(tx.get("block_timestamp", 0))
    block_height = tx.get("block", {}).get("block_height", 0)
    
    signer = tx.get("signer_account_id", "")
    receiver = tx.get("receiver_account_id", "")
    
    # Determine direction
    if receiver.lower() == account_id.lower():
        direction = "in"
        counterparty = signer
    else:
        direction = "out"
        counterparty = receiver
    
    # Get actions
    actions = tx.get("actions", [])
    action_type = "TRANSFER"
    amount = None
    method_name = None
    
    for action in actions:
        kind = action.get("action", "")
        if kind == "TRANSFER":
            action_type = "TRANSFER"
            deposit = action.get("args", {}).get("deposit", "0")
            try:
                amount = str(deposit)
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse deposit amount in TRANSFER action for tx %s: %s", tx_hash, e)
        elif kind == "FUNCTION_CALL":
            action_type = "FUNCTION_CALL"
            method_name = action.get("args", {}).get("method_name", "")
            deposit = action.get("args", {}).get("deposit", "0")
            try:
                amount = str(deposit)
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse deposit amount in FUNCTION_CALL action for tx %s: %s", tx_hash, e)
        elif kind == "CREATE_ACCOUNT":
            action_type = "CREATE_ACCOUNT"
        elif kind == "ADD_KEY":
            action_type = "ADD_KEY"
    
    return {
        "wallet_id": wallet_id,
        "tx_hash": tx_hash,
        "receipt_id": tx_hash,  # Will use tx_hash as receipt_id for simplicity
        "block_height": block_height,
        "block_timestamp": block_ts,
        "direction": direction,
        "counterparty": counterparty,
        "action_type": action_type,
        "method_name": method_name,
        "amount": amount,
        "fee": "0",
        "success": 1,
        "raw_json": json.dumps(tx),
        "asset": "NEAR"
    }

def save_transaction(conn, tx_data):
    """Insert transaction into database."""
    try:
        conn.execute("""
            INSERT INTO transactions 
            (wallet_id, tx_hash, receipt_id, block_height, block_timestamp,
             direction, counterparty, action_type, method_name, amount, fee,
             success, raw_json, asset)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_data["wallet_id"],
            tx_data["tx_hash"],
            tx_data["receipt_id"],
            tx_data["block_height"],
            tx_data["block_timestamp"],
            tx_data["direction"],
            tx_data["counterparty"],
            tx_data["action_type"],
            tx_data.get("method_name"),
            tx_data["amount"],
            tx_data["fee"],
            tx_data["success"],
            tx_data["raw_json"],
            tx_data["asset"]
        ))
        return True
    except sqlite3.IntegrityError:
        return False  # Duplicate

def main():
    with sqlite3.connect(DB_PATH) as conn:
        # Get active wallets (those with recent activity)
        wallets = conn.execute("""
            SELECT w.id, w.account_id
            FROM wallets w
            WHERE w.chain = 'NEAR'
            AND w.id IN (
                SELECT DISTINCT wallet_id FROM transactions
                WHERE block_timestamp > 1740355200000000000  -- Feb 24, 2026
            )
            ORDER BY w.id
        """).fetchall()

        print(f"Checking {len(wallets)} active wallets...")

        # Feb 25, 2026 00:00 UTC in nanoseconds
        cutoff_ts = 1740441600000000000
        total_new = 0

        for wallet_id, account_id in wallets:
            print(f"\n[{wallet_id}] {account_id}")

            # Get latest indexed timestamp for this wallet
            row = conn.execute(
                "SELECT MAX(block_timestamp) FROM transactions WHERE wallet_id = ?",
                (wallet_id,)
            ).fetchone()
            last_ts = row[0] if row and row[0] else 0

            # Fetch recent transactions
            txns = get_wallet_transactions(account_id, limit=50)
            new_count = 0

            for tx in txns:
                block_ts = int(tx.get("block_timestamp", 0))
                if block_ts <= last_ts:
                    continue  # Already have this one or older

                tx_data = parse_nearblocks_tx(tx, wallet_id, account_id)
                if save_transaction(conn, tx_data):
                    new_count += 1
                    print(f"  + {tx_data['tx_hash'][:20]}... {tx_data['direction']} {tx_data['action_type']}")

            if new_count > 0:
                conn.commit()
                total_new += new_count
                print(f"  Saved {new_count} new transactions")
            else:
                print(f"  No new transactions")

            time.sleep(0.5)  # Rate limit

    print(f"\n=== Total: {total_new} new transactions ===")

if __name__ == "__main__":
    main()
