import sqlite3

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

# Check for tx hashes that have both IN and OUT
cur.execute("""
    SELECT tx_hash, 
           SUM(CASE WHEN direction = 'in' THEN 1 ELSE 0 END) as in_cnt,
           SUM(CASE WHEN direction = 'out' THEN 1 ELSE 0 END) as out_cnt,
           SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) ELSE 0 END)/1e24 as in_near,
           SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) ELSE 0 END)/1e24 as out_near
    FROM transactions
    WHERE wallet_id = ? AND asset = 'NEAR'
    GROUP BY tx_hash
    HAVING in_cnt > 0 AND out_cnt > 0
""", (wallet_id,))

rows = cur.fetchall()
print(f"Transactions with BOTH in and out: {len(rows)}")
total_double = 0
for r in rows:
    net = min(r[3], r[4])  # The double-counted portion
    total_double += net
    if r[3] > 1 or r[4] > 1:
        print(f"  {r[0][:16]}... IN:{r[1]} ({r[3]:.4f}) OUT:{r[2]} ({r[4]:.4f})")

print(f"\nDouble-counted amount: {total_double:.4f} NEAR")

# Check total by direction
cur.execute("""
    SELECT direction, COUNT(*), SUM(CAST(amount AS REAL))/1e24
    FROM transactions
    WHERE wallet_id = ? AND asset = 'NEAR'
    GROUP BY direction
""", (wallet_id,))
print()
print("Summary by direction:")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} txs, {r[2]:.4f} NEAR")

conn.close()
