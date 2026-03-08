#!/usr/bin/env python3
"""Re-index ETH wallets using Alchemy API to capture internal transactions."""

import sqlite3
import requests
import os

ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', 'ckTIZT8on08E5QxyY8oOw')
ALCHEMY_URL = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
DB_PATH = '/home/deploy/neartax/neartax.db'

def fetch_all_transfers(address):
    """Fetch all transfers (internal + external) for an address."""
    all_transfers = []
    
    for direction in ["from", "to"]:
        page_key = None
        while True:
            params = {
                direction + "Address": address.lower(),
                "category": ["external", "internal"],
                "withMetadata": True,
                "excludeZeroValue": True,
                "maxCount": "0x3e8",  # 1000
            }
            if page_key:
                params["pageKey"] = page_key
            
            response = requests.post(ALCHEMY_URL, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "alchemy_getAssetTransfers",
                "params": [params]
            }, timeout=30)
            
            data = response.json()
            if "error" in data:
                print(f"  API Error: {data['error']}")
                break
            
            result = data.get("result", {})
            transfers = result.get("transfers", [])
            all_transfers.extend(transfers)
            
            page_key = result.get("pageKey")
            if not page_key:
                break
    
    return all_transfers

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get ETH wallets
    cursor.execute("SELECT id, account_id FROM wallets WHERE chain = 'ethereum'")
    wallets = cursor.fetchall()
    print(f"Found {len(wallets)} ETH wallets to re-index with Alchemy")
    
    total_inserted = 0
    
    for wallet_id, address in wallets:
        print(f"\nWallet {wallet_id}: {address[:14]}...")
        
        transfers = fetch_all_transfers(address)
        
        internal = sum(1 for t in transfers if t.get("category") == "internal")
        external = len(transfers) - internal
        print(f"  Found: {len(transfers)} transfers ({external} external, {internal} internal)")
        
        inserted = 0
        for t in transfers:
            from_addr = (t.get("from") or "").lower()
            to_addr = (t.get("to") or "").lower()
            addr_lower = address.lower()
            
            if from_addr == addr_lower:
                direction = "OUT"
                counterparty = to_addr
            elif to_addr == addr_lower:
                direction = "IN"
                counterparty = from_addr
            else:
                continue
            
            value = t.get("value", 0)
            if not value or value == 0:
                continue
            
            tx_hash = t.get("hash", "")
            block_num = int(t.get("blockNum", "0x0"), 16)
            timestamp = t.get("metadata", {}).get("blockTimestamp", "")
            category = t.get("category", "external")
            action_type = "INTERNAL_TRANSFER" if category == "internal" else "TRANSFER"
            
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO transactions 
                    (wallet_id, tx_hash, block_height, timestamp, action_type, 
                     direction, counterparty, amount, token_id, success, chain)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    wallet_id, tx_hash, block_num, timestamp, action_type,
                    direction, counterparty, value, "ETH", 1, "ethereum"
                ))
                if cursor.rowcount > 0:
                    inserted += 1
            except Exception as e:
                print(f"  Insert error: {e}")
        
        conn.commit()
        print(f"  Inserted: {inserted} new transactions")
        total_inserted += inserted
    
    conn.close()
    print(f"\nTotal inserted: {total_inserted}")

if __name__ == "__main__":
    main()
