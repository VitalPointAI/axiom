#!/usr/bin/env python3
"""Compare IN deposits with NearBlocks to find missing inflows."""
import sqlite3
import requests

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

print(f"Comparing IN transactions: DB vs NearBlocks for {wallet}")
print("="*60)

# Get our IN totals by counterparty
cur.execute("""
    SELECT counterparty, SUM(CAST(amount AS REAL)/1e24) as total
    FROM transactions 
    WHERE wallet_id = ? AND direction = 'in' AND counterparty != ?
    GROUP BY counterparty
    ORDER BY total DESC
""", (wallet_id, wallet))
db_by_counterparty = {r[0]: r[1] for r in cur.fetchall()}
db_total = sum(db_by_counterparty.values())

print(f"Our DB total IN: {db_total:.4f} NEAR")

# Get NearBlocks IN totals
print("\nFetching from NearBlocks...")
nb_in_total = 0
cursor = None
for _ in range(20):
    url = f"https://api.nearblocks.io/v1/account/{wallet}/txns?per_page=100"
    if cursor:
        url += f"&cursor={cursor}"
    resp = requests.get(url, timeout=15)
    data = resp.json()
    txns = data.get("txns", [])
    if not txns:
        break
    
    for tx in txns:
        receiver = tx.get("receiver_account_id", "")
        predecessor = tx.get("predecessor_account_id", "")
        
        # Only count IN to this wallet from external sources
        if receiver == wallet and predecessor != wallet:
            actions = tx.get("actions", []) or []
            for a in actions:
                if isinstance(a, dict):
                    deposit = (a.get("deposit") or 0) / 1e24
                    nb_in_total += deposit
    
    cursor = data.get("cursor")
    if not cursor:
        break

print(f"NearBlocks total IN: {nb_in_total:.4f} NEAR")
print(f"Difference: {db_total - nb_in_total:+.4f} NEAR")

# Check if the difference explains our gap
print(f"\nOur verification gap: -1.10 NEAR")
print(f"IN difference:        {db_total - nb_in_total:+.4f} NEAR")

if db_total > nb_in_total:
    print("We have MORE IN than NearBlocks - not the source of missing NEAR")
else:
    print(f"We are missing {nb_in_total - db_total:.4f} NEAR in deposits!")

conn.close()
