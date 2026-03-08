#!/usr/bin/env python3
"""Check system transactions that are being excluded."""
import sqlite3
conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

for wallet in ["vpacademy.cdao.near", "vpointai.cdao.near"]:
    cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
    wallet_id = cur.fetchone()[0]
    
    print(f"\n{'='*60}")
    print(f"{wallet}")
    print(f"{'='*60}")
    
    # Check system transactions
    cur.execute("""
        SELECT direction, action_type, COUNT(*), SUM(CAST(amount AS REAL))/1e24
        FROM transactions
        WHERE wallet_id = ? AND counterparty = 'system'
        GROUP BY direction, action_type
    """, (wallet_id,))
    
    print("System transactions (currently excluded):")
    for r in cur.fetchall():
        print(f"  {r[0]:5} {r[1]:20} {r[2]:4} txs  {r[3]:12.4f} NEAR")
    
    # Check what other counterparties are excluded
    cur.execute("""
        SELECT direction, counterparty, COUNT(*), SUM(CAST(amount AS REAL))/1e24
        FROM transactions
        WHERE wallet_id = ?
        GROUP BY direction, counterparty
        HAVING counterparty = ? OR counterparty = 'system'
    """, (wallet_id, wallet))
    
    print("\nExcluded counterparties:")
    for r in cur.fetchall():
        cp = r[1] if r[1] else "NULL"
        print(f"  {r[0]:5} {cp:25} {r[2]:4} txs  {r[3]:12.4f} NEAR")

conn.close()
