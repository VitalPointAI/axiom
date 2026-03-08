#!/usr/bin/env python3
"""Compare OUT with NearBlocks."""
import sqlite3
import requests

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

print(f"Comparing OUT transactions: DB vs NearBlocks for {wallet}")
print("="*60)

# Get our OUT totals (excluding self)
cur.execute("""
    SELECT SUM(CAST(amount AS REAL)/1e24)
    FROM transactions 
    WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
""", (wallet_id, wallet))
db_out = cur.fetchone()[0] or 0

print(f"Our DB OUT (excl self): {db_out:.4f} NEAR")

# Get NearBlocks OUT
print("\nFetching from NearBlocks...")
nb_out_total = 0
cursor = None
pages = 0
for _ in range(20):
    url = f"https://api.nearblocks.io/v1/account/{wallet}/txns?per_page=100"
    if cursor:
        url += f"&cursor={cursor}"
    resp = requests.get(url, timeout=15)
    data = resp.json()
    txns = data.get("txns", [])
    if not txns:
        break
    pages += 1
    
    for tx in txns:
        receiver = tx.get("receiver_account_id", "")
        predecessor = tx.get("predecessor_account_id", "")
        
        # Only count OUT from this wallet to external
        if predecessor == wallet and receiver != wallet:
            actions = tx.get("actions", []) or []
            for a in actions:
                if isinstance(a, dict) and a.get("action") == "TRANSFER":
                    deposit = (a.get("deposit") or 0) / 1e24
                    nb_out_total += deposit
    
    cursor = data.get("cursor")
    if not cursor:
        break

print(f"Pages fetched: {pages}")
print(f"NearBlocks OUT (TRANSFER only): {nb_out_total:.4f} NEAR")
print(f"Difference: {db_out - nb_out_total:+.4f} NEAR")

# Also check total transaction count
cur.execute("SELECT COUNT(*) FROM transactions WHERE wallet_id = ?", (wallet_id,))
db_count = cur.fetchone()[0]
print(f"\nOur DB transaction count: {db_count}")
print(f"NearBlocks says total: 403")

conn.close()
