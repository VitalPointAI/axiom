#!/usr/bin/env python3
"""Compare fees between our DB and NearBlocks."""
import sqlite3
import requests

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

print(f"Fee comparison for {wallet}")
print("="*60)

# Get NearBlocks transactions and fees
print("\nFetching from NearBlocks...")
nb_fees_by_tx = {}
cursor = None
total_nb_fee = 0

for page in range(20):
    url = f"https://api.nearblocks.io/v1/account/{wallet}/txns?per_page=100"
    if cursor:
        url += f"&cursor={cursor}"
    resp = requests.get(url, timeout=15)
    data = resp.json()
    txns = data.get("txns", [])
    if not txns:
        break

    for tx in txns:
        tx_hash = tx.get("transaction_hash", "")
        # Only count fees when this wallet is the sender (predecessor)
        if tx.get("predecessor_account_id") == wallet:
            fee = (tx.get("outcomes_agg", {}).get("transaction_fee") or 0) / 1e24
            if tx_hash not in nb_fees_by_tx:
                nb_fees_by_tx[tx_hash] = fee
                total_nb_fee += fee

    cursor = data.get("cursor")
    if not cursor:
        break

print(f"NearBlocks: {len(nb_fees_by_tx)} outgoing txs, total fees: {total_nb_fee:.6f} NEAR")

# Get our DB fees
cur.execute("""
    SELECT tx_hash, MAX(CAST(fee AS REAL)/1e24) as fee
    FROM transactions
    WHERE wallet_id = ? AND direction = 'out'
    GROUP BY tx_hash
""", (wallet_id,))
db_fees_by_tx = {r[0]: r[1] for r in cur.fetchall()}
total_db_fee = sum(db_fees_by_tx.values())

print(f"Our DB:     {len(db_fees_by_tx)} outgoing txs, total fees: {total_db_fee:.6f} NEAR")
print(f"Difference: {total_db_fee - total_nb_fee:.6f} NEAR")

# Find discrepancies
print("\nFee discrepancies (>0.001 NEAR):")
print("-"*60)
all_hashes = set(nb_fees_by_tx.keys()) | set(db_fees_by_tx.keys())
big_diffs = []
for h in all_hashes:
    nb_fee = nb_fees_by_tx.get(h, 0)
    db_fee = db_fees_by_tx.get(h, 0)
    diff = db_fee - nb_fee
    if abs(diff) > 0.001:
        big_diffs.append((h, nb_fee, db_fee, diff))

big_diffs.sort(key=lambda x: -abs(x[3]))
for h, nb, db, d in big_diffs[:10]:
    print(f"  {h[:20]}... NB:{nb:.6f}  DB:{db:.6f}  diff:{d:+.6f}")

if not big_diffs:
    print("  No significant fee discrepancies found")

conn.close()
