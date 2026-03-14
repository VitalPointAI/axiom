#!/usr/bin/env python3
"""Trace full transaction flow to find any missing receipts."""
import sqlite3
import requests

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

print(f"Tracing missing NEAR for {wallet}")
print("="*70)

# Get the gap
cur.execute("""
    SELECT 
        SUM(CASE WHEN direction = 'in' AND counterparty != ? THEN CAST(amount AS REAL)/1e24 ELSE 0 END) as in_amt,
        SUM(CASE WHEN direction = 'out' AND counterparty != ? THEN CAST(amount AS REAL)/1e24 ELSE 0 END) as out_amt
    FROM transactions WHERE wallet_id = ?
""", (wallet, wallet, wallet_id))
row = cur.fetchone()
total_in, total_out = row

cur.execute("""
    SELECT SUM(max_fee) FROM (
        SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
        FROM transactions WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
        GROUP BY tx_hash
    )
""", (wallet_id, wallet))
fees = cur.fetchone()[0] or 0

# Get RPC balance and storage
resp = requests.post("https://rpc.fastnear.com", json={
    "jsonrpc": "2.0", "id": "x", "method": "query",
    "params": {"request_type": "view_account", "finality": "final", "account_id": wallet}
}, timeout=10)
result = resp.json().get("result", {})
rpc_balance = float(result.get("amount", 0)) / 1e24
storage_usage = result.get("storage_usage", 0)
storage_cost = storage_usage * 1e-5

computed = total_in - total_out - fees
gap = computed - rpc_balance

print(f"IN (excl self):      {total_in:.6f} NEAR")
print(f"OUT (excl self):     {total_out:.6f} NEAR")
print(f"Fees:                {fees:.6f} NEAR")
print(f"Computed:            {computed:.6f} NEAR")
print(f"RPC balance:         {rpc_balance:.6f} NEAR")
print(f"Storage locked:      {storage_cost:.6f} NEAR")
print(f"GAP:                 {gap:.6f} NEAR")

# The gap should be explainable by one of:
# 1. Storage staking (locked NEAR for contract storage)
# 2. Gas refunds (not recorded as transactions)
# 3. Missing receipts

print("\n" + "="*70)
print("ANALYSIS:")
print("="*70)

# Check if gap matches storage
print("\n1. Storage check:")
print("   If storage was funded from deposits, gap should be ~= -storage")
print(f"   Storage: {storage_cost:.6f} NEAR")
print(f"   Gap:     {gap:.6f} NEAR")
print(f"   Gap + Storage = {gap + storage_cost:.6f} NEAR")

# Check total fees vs expected
print("\n2. Fee analysis:")
print(f"   Total fees recorded: {fees:.6f} NEAR")

# Check if there are any transactions with unusual amounts
print("\n3. Checking for precision issues:")
cur.execute("""
    SELECT COUNT(*) FROM transactions 
    WHERE wallet_id = ? AND (
        CAST(amount AS REAL) != ROUND(CAST(amount AS REAL), 0)
    )
""", (wallet_id,))
non_round = cur.fetchone()[0]
print(f"   Transactions with non-integer yoctoNEAR amounts: {non_round}")

# The most likely explanation
print("\n4. Likely explanation:")
if abs(gap + storage_cost) < 0.5:
    print("   Gap is approximately equal to storage cost.")
    print("   The storage was funded from initial deposits but isn't counted as OUT.")
else:
    print(f"   Gap ({gap:.4f}) doesn't match storage ({storage_cost:.4f})")
    print("   The gap is likely from accumulated gas refunds and precision.")
    print("   Gas refunds happen automatically without creating transactions.")

conn.close()
