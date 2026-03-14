#!/usr/bin/env python3
"""Calculate balance with corrected fee attribution."""
import sqlite3
import requests

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

print(f"Corrected balance calculation for {wallet}")
print("="*60)

# IN (excluding self)
cur.execute("""
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0)
    FROM transactions
    WHERE wallet_id = ? AND direction = 'in' AND counterparty != ?
""", (wallet_id, wallet))
total_in = cur.fetchone()[0]

# OUT (excluding self)
cur.execute("""
    SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0)
    FROM transactions
    WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
""", (wallet_id, wallet))
total_out = cur.fetchone()[0]

# OLD fee calculation: MAX per tx_hash for all OUT
cur.execute("""
    SELECT COALESCE(SUM(max_fee), 0) FROM (
        SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
        FROM transactions
        WHERE wallet_id = ? AND direction = 'out'
        GROUP BY tx_hash
    )
""", (wallet_id,))
old_fees = cur.fetchone()[0]

# NEW fee calculation: MAX per tx_hash, excluding self-transfers
cur.execute("""
    SELECT COALESCE(SUM(max_fee), 0) FROM (
        SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
        FROM transactions
        WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
        GROUP BY tx_hash
    )
""", (wallet_id, wallet))
new_fees = cur.fetchone()[0]

# Get RPC balance
resp = requests.post("https://rpc.fastnear.com", json={
    "jsonrpc": "2.0", "id": "verify",
    "method": "query",
    "params": {"request_type": "view_account", "finality": "final", "account_id": wallet}
}, timeout=10)
rpc_balance = float(resp.json().get("result", {}).get("amount", 0)) / 1e24

# Calculate both ways
old_computed = total_in - total_out - old_fees
new_computed = total_in - total_out - new_fees

print(f"IN (excl self):      {total_in:12.4f} NEAR")
print(f"OUT (excl self):     {total_out:12.4f} NEAR")
print()
print(f"OLD fees (all OUT):  {old_fees:12.6f} NEAR")
print(f"NEW fees (no self):  {new_fees:12.6f} NEAR")
print(f"Fee difference:      {old_fees - new_fees:12.6f} NEAR")
print()
print(f"OLD computed:        {old_computed:12.4f} NEAR")
print(f"NEW computed:        {new_computed:12.4f} NEAR")
print(f"RPC balance:         {rpc_balance:12.4f} NEAR")
print()
print(f"OLD diff:            {old_computed - rpc_balance:+12.4f} NEAR")
print(f"NEW diff:            {new_computed - rpc_balance:+12.4f} NEAR")
print()

# What if we ALSO count tx_hashes where we're not the original signer?
# The signer pays the fee, not the receiver
print("="*60)
print("Verifying fee attribution:")

# Get tx_hashes where this wallet initiated (direction=out to external)
cur.execute("""
    SELECT DISTINCT tx_hash FROM transactions
    WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
""", (wallet_id, wallet))
our_initiated_txs = set(r[0] for r in cur.fetchall())

# Now check: how many unique tx_hashes have fees attributed to us?
cur.execute("""
    SELECT COUNT(DISTINCT tx_hash) FROM transactions
    WHERE wallet_id = ? AND direction = 'out' AND CAST(fee AS REAL) > 0
""", (wallet_id,))
total_fee_txs = cur.fetchone()[0]

print(f"Tx hashes we initiated (OUT to external): {len(our_initiated_txs)}")
print(f"Tx hashes with fees attributed:           {total_fee_txs}")

conn.close()
