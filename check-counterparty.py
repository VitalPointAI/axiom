#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

# Check what counterparty values look like for self-transfers
cur.execute("""
    SELECT counterparty, COUNT(*), SUM(CAST(amount AS REAL))/1e24
    FROM transactions
    WHERE wallet_id = ? AND direction = 'out'
    GROUP BY counterparty
    ORDER BY SUM(CAST(amount AS REAL)) DESC
    LIMIT 10
""", (wallet_id,))

print("Counterparty values for OUT transactions:")
for r in cur.fetchall():
    cp = repr(r[0])  # Show exact value including None
    print(f"  {cp:45} {r[1]:4} txs  {r[2]:12.4f} NEAR")

conn.close()
