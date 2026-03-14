#!/usr/bin/env python3
"""Find the missing transactions by comparing DB with NearBlocks."""
import sqlite3
import requests
import time

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

print(f"Finding missing transactions for {wallet}")
print("="*70)

# Get all our tx_hashes
cur.execute("SELECT DISTINCT tx_hash FROM transactions WHERE wallet_id = ?", (wallet_id,))
our_hashes = set(r[0] for r in cur.fetchall())
print(f"Our DB has {len(our_hashes)} unique tx_hashes")

# Get all NearBlocks tx_hashes
print("\nFetching all transactions from NearBlocks...")
nb_hashes = set()
nb_txns = {}  # tx_hash -> tx data
cursor = None
pages = 0

while pages < 30:
    url = f"https://api.nearblocks.io/v1/account/{wallet}/txns?per_page=100"
    if cursor:
        url += f"&cursor={cursor}"

    try:
        resp = requests.get(url, timeout=30)
        data = resp.json()
    except Exception as e:
        print(f"  Error on page {pages}: {e}")
        time.sleep(2)
        continue

    txns = data.get("txns", [])
    if not txns:
        break

    pages += 1
    for tx in txns:
        tx_hash = tx.get("transaction_hash", "")
        if tx_hash:
            nb_hashes.add(tx_hash)
            if tx_hash not in nb_txns:
                nb_txns[tx_hash] = tx

    cursor = data.get("cursor")
    print(f"  Page {pages}: fetched {len(txns)} txns, total unique: {len(nb_hashes)}")

    if not cursor:
        break

    time.sleep(0.3)  # Rate limit

print(f"\nNearBlocks has {len(nb_hashes)} unique tx_hashes")

# Find missing
missing = nb_hashes - our_hashes
extra = our_hashes - nb_hashes

print(f"\nMissing from our DB: {len(missing)}")
print(f"Extra in our DB (not in NearBlocks): {len(extra)}")

if missing:
    print("\n" + "="*70)
    print("MISSING TRANSACTIONS (need to index these):")
    print("="*70)

    for tx_hash in sorted(missing):
        tx = nb_txns.get(tx_hash, {})
        predecessor = tx.get("predecessor_account_id", "?")
        receiver = tx.get("receiver_account_id", "?")
        actions = tx.get("actions", [])

        # Get deposit and action type
        action_info = []
        total_deposit = 0
        for a in actions:
            if isinstance(a, dict):
                action_type = a.get("action", "?")
                deposit = (a.get("deposit") or 0) / 1e24
                total_deposit += deposit
                action_info.append(f"{action_type}({deposit:.4f})")

        # Check receipt status
        receipt_outcome = tx.get("receipt_outcome", {})
        status = receipt_outcome.get("status", "?")

        print(f"\n  TX: {tx_hash}")
        print(f"    From: {predecessor} -> To: {receiver}")
        print(f"    Actions: {', '.join(action_info) if action_info else 'N/A'}")
        print(f"    Total deposit: {total_deposit:.4f} NEAR")
        print(f"    Receipt status: {status}")

if extra:
    print(f"\n(Extra {len(extra)} tx_hashes in DB but not in NearBlocks - may be from different pagination)")

conn.close()
