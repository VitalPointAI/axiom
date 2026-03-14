#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/agent/openclaw/projects/neartax')
from indexers.near_indexer import index_account
from db.init import get_connection

conn = get_connection()
wallets = conn.execute("SELECT account_id FROM wallets WHERE account_id LIKE '%.near' OR length(account_id) = 64").fetchall()
conn.close()

print(f"Indexing {len(wallets)} wallets...")
for i, (account_id,) in enumerate(wallets):
    print(f"[{i+1}/{len(wallets)}] {account_id}")
    try:
        count = index_account(account_id)
        print(f"  -> {count} transactions")
    except Exception as e:
        print(f"  -> Error: {e}")

print("Done!")
