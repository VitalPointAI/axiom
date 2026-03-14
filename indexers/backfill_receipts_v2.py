#!/usr/bin/env python3
"""
Backfill missing receipt-level transfers for contract wallets.
Shows progress as it runs.
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from indexers.nearblocks_client import NearBlocksClient

print("Starting receipt backfill...", flush=True)

# Contract patterns
CONTRACT_PATTERNS = [".credz.near", ".isnft.near", ".cdao.near"]

def is_contract(account):
    return any(p in account for p in CONTRACT_PATTERNS)

# Get contract wallets
conn = get_connection()
rows = conn.execute("SELECT id, account_id FROM wallets WHERE chain = 'NEAR'").fetchall()
conn.close()

wallets = [(r[0], r[1]) for r in rows if is_contract(r[1])]
print(f"Found {len(wallets)} contract wallets to process", flush=True)

client = NearBlocksClient()
total_added = 0

for idx, (wallet_id, account_id) in enumerate(wallets):
    print(f"\n[{idx+1}/{len(wallets)}] Processing {account_id}...", flush=True)
    
    conn = get_connection()
    cursor = None
    added = 0
    pages = 0
    
    while True:
        try:
            result = client.fetch_receipts(account_id, cursor=cursor, per_page=100)
        except Exception as e:
            print(f"    API error: {e}", flush=True)
            break
            
        receipts = result.get("txns", [])
        if not receipts:
            break
        
        pages += 1
        
        for r in receipts:
            if r.get("predecessor_account_id") != account_id:
                continue
            
            for action in r.get("actions", []):
                if action.get("action") != "TRANSFER":
                    continue
                
                deposit = action.get("deposit", 0)
                if not deposit or float(deposit) < 1e18:
                    continue
                
                tx_hash = r.get("transaction_hash", "")
                receipt_id = r.get("receipt_id", "")
                receiver = r.get("receiver_account_id", "")
                
                existing = conn.execute(
                    "SELECT 1 FROM transactions WHERE wallet_id = ? AND receipt_id = ?",
                    (wallet_id, receipt_id)
                ).fetchone()
                
                if existing:
                    continue
                
                try:
                    conn.execute("""
                        INSERT INTO transactions 
                        (tx_hash, receipt_id, wallet_id, direction, counterparty, 
                         action_type, amount, fee, block_height, block_timestamp, success)
                        VALUES (?, ?, ?, 'out', ?, 'TRANSFER', ?, '0', ?, ?, 1)
                    """, (
                        tx_hash,
                        receipt_id,
                        wallet_id,
                        receiver,
                        str(int(float(deposit))),
                        r.get("receipt_block", {}).get("block_height", 0),
                        r.get("block_timestamp", "")
                    ))
                    added += 1
                except Exception as e:
                    print(f"    Insert error: {e}", flush=True)
        
        cursor = result.get("cursor")
        if not cursor:
            break
    
    conn.commit()
    conn.close()
    
    if added > 0:
        print(f"  ✓ Added {added} transfers ({pages} pages)", flush=True)
        total_added += added
    else:
        print(f"  - No new transfers ({pages} pages)", flush=True)

print(f"\n✅ Done! Added {total_added} total receipt transfers", flush=True)
