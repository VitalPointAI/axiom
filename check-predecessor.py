#!/usr/bin/env python3
"""Check if any OUT transactions have predecessor != our wallet."""
import sqlite3
import json

with sqlite3.connect("neartax.db") as conn:
    cur = conn.cursor()
    try:
        wallet = "vpacademy.cdao.near"
        cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
        wallet_id = cur.fetchone()[0]

        print(f"Checking predecessor for OUT transactions in {wallet}")
        print("="*60)

        # Check all OUT transactions with raw_json
        cur.execute("""
            SELECT tx_hash, counterparty, CAST(fee AS REAL)/1e24, raw_json
            FROM transactions
            WHERE wallet_id = ? AND direction = 'out' AND raw_json IS NOT NULL
        """, (wallet_id,))

        our_wallet_count = 0
        other_predecessor_count = 0
        other_fees = 0
        other_examples = []

        for row in cur.fetchall():
            tx_hash, cp, fee, raw_json = row
            tx = json.loads(raw_json)
            predecessor = tx.get('predecessor_account_id', '')

            if predecessor == wallet:
                our_wallet_count += 1
            else:
                other_predecessor_count += 1
                other_fees += fee
                if len(other_examples) < 5:
                    other_examples.append((tx_hash, predecessor, cp, fee))

        print(f"OUT txs where we are predecessor: {our_wallet_count}")
        print(f"OUT txs where OTHER is predecessor: {other_predecessor_count}")
        print(f"Fees on 'other' txs: {other_fees:.6f} NEAR")

        if other_examples:
            print("\nExamples of 'other' predecessor (shouldn't have fees):")
            for tx_hash, pred, cp, fee in other_examples:
                print(f"  {tx_hash[:16]}... pred={pred[:20]}, cp={cp}, fee={fee:.6f}")

        # Also check: for txs without raw_json, how are they handled?
        cur.execute("""
            SELECT COUNT(*), SUM(CAST(fee AS REAL)/1e24)
            FROM transactions
            WHERE wallet_id = ? AND direction = 'out' AND raw_json IS NULL
        """, (wallet_id,))
        row = cur.fetchone()
        print(f"\nOUT txs without raw_json: {row[0]}, fees: {row[1] or 0:.6f} NEAR")
    finally:
        cur.close()
