#!/usr/bin/env python3
"""Efficient bulk price update using SQL"""
import sqlite3

conn = sqlite3.connect("/home/deploy/neartax/neartax.db")
cur = conn.cursor()

print("Creating temp price lookup table...")

# Create price lookup
cur.execute("""
    CREATE TEMP TABLE daily_prices AS
    SELECT
        SUBSTR(date, 1, 10) as price_date,
        price as usd_price,
        price * 1.38 as cad_price
    FROM price_cache
    WHERE coin_id = "NEAR" AND currency = "USD"
""")
cur.execute("CREATE INDEX idx_dp ON daily_prices(price_date)")

print("Bulk updating transactions...")

# Single bulk update
cur.execute("""
    UPDATE transactions
    SET
        cost_basis_usd = (CAST(amount AS REAL) / 1e24) * (
            SELECT usd_price FROM daily_prices
            WHERE price_date = DATE(block_timestamp / 1000000000, "unixepoch")
            LIMIT 1
        ),
        cost_basis_cad = (CAST(amount AS REAL) / 1e24) * (
            SELECT cad_price FROM daily_prices
            WHERE price_date = DATE(block_timestamp / 1000000000, "unixepoch")
            LIMIT 1
        )
    WHERE block_timestamp IS NOT NULL
    AND amount IS NOT NULL
    AND CAST(amount AS REAL) > 1e20
    AND (cost_basis_cad IS NULL OR cost_basis_cad = 0)
""")

conn.commit()
print(f"Updated {cur.rowcount} rows")

# Verify
cur.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN cost_basis_cad > 0 THEN 1 ELSE 0 END) as priced,
        SUM(CASE WHEN cost_basis_cad IS NULL OR cost_basis_cad = 0 THEN 1 ELSE 0 END) as unpriced
    FROM transactions
    WHERE amount IS NOT NULL AND CAST(amount AS REAL) > 1e20
""")
print("Result:", cur.fetchone())

conn.close()
print("Done!")
