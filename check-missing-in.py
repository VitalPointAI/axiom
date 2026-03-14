#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

print("Checking for missing IN sources:")
print("="*60)

# Check if any IN transactions have negative amounts (refunds?)
cur.execute("""
    SELECT action_type, method_name, direction, COUNT(*), SUM(CAST(amount AS REAL)/1e24)
    FROM transactions
    WHERE wallet_id = ? AND CAST(amount AS REAL) < 0
    GROUP BY action_type, method_name, direction
""", (wallet_id,))
rows = cur.fetchall()
if rows:
    print("\nTransactions with NEGATIVE amounts (possible refunds):")
    for r in rows:
        method = r[1] if r[1] else "-"
        print(f"  {r[0]:20} {method:20} {r[2]:5} {r[3]} txs {r[4]:.4f} NEAR")
else:
    print("\nNo negative amount transactions found")

# Check CREATE_ACCOUNT transaction - initial funding
print("\nCREATE_ACCOUNT transactions:")
cur.execute("""
    SELECT tx_hash, direction, counterparty, CAST(amount AS REAL)/1e24
    FROM transactions
    WHERE wallet_id = ? AND action_type = 'CREATE_ACCOUNT'
""", (wallet_id,))
for r in cur.fetchall():
    print(f"  {r[0][:20]}... {r[1]} from {r[2]} - {r[3]:.4f} NEAR")

# Check the very first transactions chronologically
print("\nFirst 5 transactions (chronological):")
cur.execute("""
    SELECT tx_hash, action_type, direction, counterparty, CAST(amount AS REAL)/1e24,
           datetime(block_timestamp/1000000000, 'unixepoch')
    FROM transactions
    WHERE wallet_id = ?
    ORDER BY block_timestamp ASC
    LIMIT 5
""", (wallet_id,))
for r in cur.fetchall():
    cp = (r[3] or "")[:20]
    print(f"  {r[5]} | {r[1]:15} {r[2]:5} {cp:20} {r[4]:.4f} NEAR")

# Check if there are any transactions from "system" that are IN
print("\nIN transactions by counterparty:")
cur.execute("""
    SELECT counterparty, COUNT(*), SUM(CAST(amount AS REAL)/1e24)
    FROM transactions
    WHERE wallet_id = ? AND direction = 'in'
    GROUP BY counterparty
    ORDER BY SUM(CAST(amount AS REAL)) DESC
""", (wallet_id,))
for r in cur.fetchall()[:15]:
    cp = r[0] if r[0] else "NULL"
    print(f"  {cp:35} {r[1]:4} txs  {r[2]:10.4f} NEAR")

# Check total IN we might be missing
print("\n" + "="*60)
print("Diagnosis:")

# All IN
cur.execute("""
    SELECT SUM(CAST(amount AS REAL)/1e24) FROM transactions
    WHERE wallet_id = ? AND direction = 'in'
""", (wallet_id,))
all_in = cur.fetchone()[0] or 0

# IN excluding self
cur.execute("""
    SELECT SUM(CAST(amount AS REAL)/1e24) FROM transactions
    WHERE wallet_id = ? AND direction = 'in' AND counterparty != ?
""", (wallet_id, wallet))
in_excl_self = cur.fetchone()[0] or 0

print(f"Total IN (all):        {all_in:12.4f} NEAR")
print(f"IN (excl self):        {in_excl_self:12.4f} NEAR")
print(f"Self IN:               {all_in - in_excl_self:12.4f} NEAR")

# Check if there are any IN with self as counterparty
cur.execute("""
    SELECT action_type, COUNT(*), SUM(CAST(amount AS REAL)/1e24)
    FROM transactions
    WHERE wallet_id = ? AND direction = 'in' AND counterparty = ?
    GROUP BY action_type
""", (wallet_id, wallet))
print("\nSelf-to-self IN transactions (should these count?):")
for r in cur.fetchall():
    print(f"  {r[0]:20} {r[1]:4} txs  {r[2]:10.4f} NEAR")

conn.close()
