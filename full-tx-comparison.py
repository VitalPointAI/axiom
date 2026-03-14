#!/usr/bin/env python3
"""Complete comparison of all transactions."""
import sqlite3
import requests
import time

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

print(f"Full transaction comparison for {wallet}")
print("="*70)

# Get NearBlocks transaction count
try:
    resp = requests.get(f"https://api.nearblocks.io/v1/account/{wallet}/txns/count", timeout=10)
    nb_count = int(resp.json().get("txns", [{}])[0].get("count", 0))
    print(f"NearBlocks total count: {nb_count}")
except Exception as e:
    print(f"Error getting count: {e}")
    nb_count = 0

# Get our count
cur.execute("SELECT COUNT(*) FROM transactions WHERE wallet_id = ?", (wallet_id,))
our_count = cur.fetchone()[0]
print(f"Our DB count: {our_count}")

# Fetch ALL transactions from NearBlocks
print("\nFetching ALL receipts from NearBlocks (this may take a moment)...")
all_nb_receipts = []
cursor = None
pages = 0

while True:
    url = f"https://api.nearblocks.io/v1/account/{wallet}/txns?per_page=100"
    if cursor:
        url += f"&cursor={cursor}"

    try:
        resp = requests.get(url, timeout=30)
        data = resp.json()
    except Exception as e:
        print(f"  Error: {e}")
        time.sleep(2)
        continue

    txns = data.get("txns", [])
    if not txns:
        break

    pages += 1
    all_nb_receipts.extend(txns)
    cursor = data.get("cursor")

    if pages % 5 == 0:
        print(f"  Fetched {len(all_nb_receipts)} receipts...")

    if not cursor:
        break

    time.sleep(0.2)

print(f"\nTotal NearBlocks receipts fetched: {len(all_nb_receipts)}")

# Analyze
nb_tx_hashes = set()
failed_receipts = []
successful_receipts = []

for tx in all_nb_receipts:
    tx_hash = tx.get("transaction_hash", "")
    receipt_outcome = tx.get("receipt_outcome", {})
    status = receipt_outcome.get("status", True)

    nb_tx_hashes.add(tx_hash)

    if status is False:
        failed_receipts.append(tx)
    else:
        successful_receipts.append(tx)

print(f"Unique tx_hashes: {len(nb_tx_hashes)}")
print(f"Successful receipts: {len(successful_receipts)}")
print(f"Failed receipts: {len(failed_receipts)}")

# Get our tx_hashes
cur.execute("SELECT DISTINCT tx_hash FROM transactions WHERE wallet_id = ?", (wallet_id,))
our_hashes = set(r[0] for r in cur.fetchall())
print(f"\nOur DB unique tx_hashes: {len(our_hashes)}")

# Compare
missing = nb_tx_hashes - our_hashes
extra = our_hashes - nb_tx_hashes

print(f"\nMissing from DB (in NearBlocks but not in DB): {len(missing)}")
print(f"Extra in DB (in DB but not in NearBlocks): {len(extra)}")

# Check the missing ones
if missing:
    print("\n--- MISSING TRANSACTIONS ---")
    for tx_hash in sorted(missing):
        # Find this tx in our fetched data
        for tx in all_nb_receipts:
            if tx.get("transaction_hash") == tx_hash:
                status = tx.get("receipt_outcome", {}).get("status", "?")
                actions = tx.get("actions", [])
                deposit = sum((a.get("deposit") or 0) / 1e24 for a in actions if isinstance(a, dict))
                print(f"  {tx_hash[:30]}... status={status} deposit={deposit:.4f}")
                break

# Sum up what we might be missing
print("\n" + "="*70)
print("ANALYSIS:")

# Calculate deposit on failed receipts
failed_deposit = 0
for tx in failed_receipts:
    actions = tx.get("actions", [])
    for a in actions:
        if isinstance(a, dict):
            failed_deposit += (a.get("deposit") or 0) / 1e24

print(f"Total deposit in FAILED receipts: {failed_deposit:.4f} NEAR")
print("(Failed receipts are correctly skipped - deposits refunded)")

conn.close()
