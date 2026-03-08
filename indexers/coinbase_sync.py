#!/usr/bin/env python3
"""
Coinbase Transaction Sync using official SDK
"""
import json
import sqlite3
import hashlib
from datetime import datetime

DB_PATH = '/home/deploy/neartax/neartax.db'
CREDS_PATH = '/home/deploy/neartax/.credentials/coinbase.json'

def sync_coinbase(user_id: int):
    from coinbase.rest import RESTClient
    
    creds = json.load(open(CREDS_PATH))
    client = RESTClient(api_key=creds["key_name"], api_secret=creds["private_key"])
    
    print("Fetching Coinbase accounts...")
    accounts = client.get_accounts()
    print(f"Found {len(accounts.accounts)} accounts")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create import batch
    cursor.execute("""
        INSERT INTO import_batches (user_id, filename, exchange, row_count)
        VALUES (?, 'Coinbase API Sync', 'coinbase', 0)
    """, (user_id,))
    batch_id = cursor.lastrowid
    
    inserted = 0
    skipped = 0
    total_txs = 0
    
    for acc in accounts.accounts:
        currency = acc.currency
        account_uuid = acc.uuid
        
        # Get transactions for this account
        try:
            # Get fills (trades)
            fills = client.get_fills(product_id=f"{currency}-USD", limit=500)
            for fill in getattr(fills, 'fills', []):
                total_txs += 1
                side = fill.side  # BUY or SELL
                size = float(fill.size)
                price = float(fill.price)
                fee = float(getattr(fill, 'commission', 0) or 0)
                trade_time = fill.trade_time
                trade_id = fill.trade_id
                
                tx_type = "buy" if side == "BUY" else "sell"
                hash_input = f"{trade_time}|{currency}|{size}|{side}|{trade_id}"
                tx_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:32]
                
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO manual_transactions 
                        (user_id, import_batch_id, timestamp, tx_type, asset, amount,
                         quote_asset, quote_amount, price_per_unit, fee_amount, fee_asset,
                         exchange, tx_id, description, hash)
                        VALUES (?, ?, ?, ?, ?, ?, 'USD', ?, ?, ?, 'USD', 'coinbase', ?, ?, ?)
                    """, (
                        user_id, batch_id, trade_time, tx_type, currency,
                        size, size * price, price, fee,
                        trade_id, f"{side} {currency}", tx_hash
                    ))
                    if cursor.rowcount > 0:
                        inserted += 1
                    else:
                        skipped += 1
                except Exception as e:
                    print(f"  Insert error: {e}")
                    skipped += 1
        except Exception as e:
            # Not all currencies have USD pairs
            pass
    
    # Update batch
    cursor.execute("""
        UPDATE import_batches 
        SET status = 'completed',
            row_count = ?,
            imported_count = ?,
            skipped_count = ?,
            completed_at = datetime('now')
        WHERE id = ?
    """, (total_txs, inserted, skipped, batch_id))
    
    conn.commit()
    conn.close()
    
    print(f"\nDone! Total: {total_txs}, Inserted: {inserted}, Skipped: {skipped}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        user_id = int(sys.argv[1])
        sync_coinbase(user_id)
    else:
        print("Usage: python3 coinbase_sync.py <user_id>")
