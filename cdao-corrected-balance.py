#!/usr/bin/env python3
"""Calculate CDAO balance excluding internal (self) transfers."""

import sqlite3
import requests

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

for wallet in ["vpacademy.cdao.near", "vpointai.cdao.near"]:
    cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
    wallet_id = cur.fetchone()[0]
    
    print(f"\n{'='*60}")
    print(f"{wallet}")
    print(f"{'='*60}")
    
    # Total IN (all sources)
    cur.execute("""
        SELECT SUM(CAST(amount AS REAL))/1e24
        FROM transactions
        WHERE wallet_id = ? AND direction = 'in' AND asset = 'NEAR'
    """, (wallet_id,))
    total_in = cur.fetchone()[0] or 0
    
    # Total OUT (all targets)
    cur.execute("""
        SELECT SUM(CAST(amount AS REAL))/1e24
        FROM transactions
        WHERE wallet_id = ? AND direction = 'out' AND asset = 'NEAR'
    """, (wallet_id,))
    total_out = cur.fetchone()[0] or 0
    
    # Self-transfers OUT (internal - should not count)
    cur.execute("""
        SELECT SUM(CAST(amount AS REAL))/1e24
        FROM transactions
        WHERE wallet_id = ? AND direction = 'out' AND asset = 'NEAR'
        AND counterparty = ?
    """, (wallet_id, wallet))
    self_out = cur.fetchone()[0] or 0
    
    # Fees
    cur.execute("""
        SELECT SUM(CAST(fee AS REAL))/1e24
        FROM transactions
        WHERE wallet_id = ? AND asset = 'NEAR'
    """, (wallet_id,))
    total_fees = cur.fetchone()[0] or 0
    
    # Corrected calculation
    actual_out = total_out - self_out
    computed = total_in - actual_out - total_fees
    
    # Get RPC balance
    resp = requests.post("https://rpc.mainnet.near.org", json={
        "jsonrpc": "2.0", "id": "x",
        "method": "query",
        "params": {"request_type": "view_account", "finality": "final", "account_id": wallet}
    }, timeout=10)
    rpc_balance = int(resp.json()["result"]["amount"]) / 1e24
    
    diff = computed - rpc_balance
    
    print(f"Total IN:           {total_in:12.4f} NEAR")
    print(f"Total OUT:          {total_out:12.4f} NEAR")
    print(f"Self-transfers:     {self_out:12.4f} NEAR (excluded)")
    print(f"Actual OUT:         {actual_out:12.4f} NEAR")
    print(f"Fees:               {total_fees:12.6f} NEAR")
    print(f"Computed:           {computed:12.4f} NEAR")
    print(f"RPC Balance:        {rpc_balance:12.4f} NEAR")
    print(f"Difference:         {diff:+12.4f} NEAR")

conn.close()
