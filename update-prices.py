#!/usr/bin/env python3
"""Bulk update transaction cost basis using price_cache"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect("/home/deploy/neartax/neartax.db")
cur = conn.cursor()

# Load NEAR prices into memory (date -> price mapping)
cur.execute("SELECT date, price FROM price_cache WHERE coin_id = ? AND currency = ?", ("NEAR", "USD"))
price_map = {}
for row in cur.fetchall():
    date_str = row[0].split()[0]  # Get just the date part (YYYY-MM-DD)
    price_map[date_str] = row[1]

print(f"Loaded {len(price_map)} NEAR daily prices")

# Default CAD rate
DEFAULT_CAD_RATE = 1.38

# Get transactions without prices
cur.execute("""
    SELECT id, block_timestamp, CAST(amount AS REAL) / 1e24 as amount_near
    FROM transactions
    WHERE block_timestamp IS NOT NULL
    AND amount IS NOT NULL
    AND CAST(amount AS REAL) > 1e20
    AND (cost_basis_cad IS NULL OR cost_basis_cad = 0)
""")
transactions = cur.fetchall()
print(f"Found {len(transactions)} transactions to price")

updated = 0
missing_price = 0

for tx_id, timestamp_ns, amount in transactions:
    if not timestamp_ns or not amount:
        continue
    
    # Convert nanoseconds to date
    try:
        dt = datetime.utcfromtimestamp(timestamp_ns / 1_000_000_000)
        date_str = dt.strftime("%Y-%m-%d")
    except Exception:
        continue
    
    price = price_map.get(date_str)
    if not price:
        # Try nearby dates
        for delta in range(1, 8):
            prev_date = (dt.replace(day=dt.day) - __import__("datetime").timedelta(days=delta)).strftime("%Y-%m-%d")
            if prev_date in price_map:
                price = price_map[prev_date]
                break
    
    if not price:
        missing_price += 1
        continue
    
    cost_usd = amount * price
    cost_cad = cost_usd * DEFAULT_CAD_RATE
    
    cur.execute("""
        UPDATE transactions 
        SET cost_basis_usd = ?, cost_basis_cad = ?
        WHERE id = ?
    """, (cost_usd, cost_cad, tx_id))
    updated += 1
    
    if updated % 10000 == 0:
        print(f"Updated {updated} transactions...")
        conn.commit()

conn.commit()
print(f"\nDone! Updated {updated} transactions, {missing_price} missing prices")

# Verify
cur.execute("SELECT COUNT(*) FROM transactions WHERE cost_basis_cad > 0")
priced = cur.fetchone()[0]
print(f"Total priced transactions: {priced}")

conn.close()
