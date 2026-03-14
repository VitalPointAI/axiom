#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

# Get a sample OUT transaction with fee to check its structure
cur.execute("""
    SELECT tx_hash, direction, counterparty, CAST(fee AS REAL)/1e24, raw_json
    FROM transactions
    WHERE wallet_id = ? AND direction = 'out' AND counterparty = 'emmitt.near'
      AND CAST(fee AS REAL) > 0
    LIMIT 1
""", (wallet_id,))
row = cur.fetchone()
if row:
    tx_hash, direction, cp, fee, raw_json = row
    print(f"Sample TX: {tx_hash[:20]}...")
    print(f"Direction: {direction}, Counterparty: {cp}, Fee: {fee:.6f}")

    if raw_json:
        tx = json.loads(raw_json)
        print("\nTransaction structure:")
        print(f"  predecessor_account_id: {tx.get('predecessor_account_id')}")
        print(f"  receiver_account_id: {tx.get('receiver_account_id')}")

        # Check for signer info
        for key in ['signer_id', 'signer_account_id', 'originator', 'origin']:
            if key in tx:
                print(f"  {key}: {tx.get(key)}")

        # Check all keys
        print(f"\n  Top-level keys: {list(tx.keys())}")

        # The key insight: if predecessor != our wallet, this is a cross-contract call
        # and we shouldn't attribute the fee to us
        predecessor = tx.get('predecessor_account_id', '')
        if predecessor == wallet:
            print("\n  -> This wallet IS the predecessor (we initiated)")
        else:
            print(f"\n  -> This wallet is NOT the predecessor ({predecessor} initiated)")
            print("  -> Fee should NOT be attributed to us!")
else:
    print("No matching transaction found")

conn.close()
