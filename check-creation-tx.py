#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

# Check the creation transaction
print("Creation transaction details:")
cur.execute("""
    SELECT tx_hash, receipt_id, action_type, direction, counterparty,
           CAST(amount AS REAL)/1e24, CAST(fee AS REAL)/1e24
    FROM transactions
    WHERE wallet_id = ? AND tx_hash LIKE 'B3TfR9%'
    ORDER BY receipt_id
""", (wallet_id,))
for r in cur.fetchall():
    print(f"  {r[0][:20]}... {r[1][:20] if r[1] else 'N/A'}")
    print(f"    action={r[2]} dir={r[3]} cp={r[4]}")
    print(f"    amount={r[5]:.4f} fee={r[6]:.6f}")

# First 5 transactions chronologically
print("\nFirst 5 transactions chronologically:")
cur.execute("""
    SELECT datetime(block_timestamp/1000000000, 'unixepoch') as dt,
           tx_hash, action_type, method_name, direction, counterparty,
           CAST(amount AS REAL)/1e24
    FROM transactions WHERE wallet_id = ?
    ORDER BY block_timestamp ASC
    LIMIT 5
""", (wallet_id,))
for r in cur.fetchall():
    method = r[3] if r[3] else '-'
    cp = r[5][:20] if r[5] else '-'
    print(f"  {r[0]} | {r[2]:15} {method:20} {r[4]:4} {cp:20} {r[6]:.4f} NEAR")

# Sum of ALL IN transactions
print("\nTotal IN by source:")
cur.execute("""
    SELECT counterparty, action_type, COUNT(*), SUM(CAST(amount AS REAL)/1e24)
    FROM transactions WHERE wallet_id = ? AND direction = 'in'
    GROUP BY counterparty, action_type
    ORDER BY SUM(CAST(amount AS REAL)) DESC
""", (wallet_id,))
for r in cur.fetchall():
    cp = r[0] if r[0] else '-'
    print(f"  {cp:30} {r[1]:15} {r[2]:3} txs {r[3]:10.4f} NEAR")

conn.close()
