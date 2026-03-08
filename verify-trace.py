#!/usr/bin/env python3
"""Trace through the exact verification logic from the route."""
import sqlite3
import requests

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

for wallet in ["vpacademy.cdao.near", "vpointai.cdao.near"]:
    cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
    wallet_id = cur.fetchone()[0]
    
    print(f"\n{'='*60}")
    print(f"VERIFICATION TRACE: {wallet}")
    print(f"{'='*60}")
    
    # Get RPC balance
    resp = requests.post("https://rpc.fastnear.com", json={
        "jsonrpc": "2.0", "id": "verify",
        "method": "query",
        "params": {"request_type": "view_account", "finality": "final", "account_id": wallet}
    }, timeout=10)
    result = resp.json().get("result", {})
    onChain = float(result.get("amount", 0)) / 1e24
    storageUsage = result.get("storage_usage", 0)
    storageCost = storageUsage * 1e-5
    
    print(f"RPC Balance:       {onChain:12.4f} NEAR")
    print(f"Storage:           {storageUsage} bytes (~{storageCost:.4f} NEAR)")
    
    # IN: exclude self-transfers AND system gas refunds
    cur.execute("""
        SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
        FROM transactions 
        WHERE wallet_id = ? 
          AND direction = 'in' 
          AND counterparty != ?
          AND counterparty != 'system'
    """, (wallet_id, wallet))
    inSum = cur.fetchone()[0]
    print(f"IN (excl self):    {inSum:12.4f} NEAR")
    
    # DELETE_ACCOUNT beneficiary transfers
    cur.execute("""
        SELECT COALESCE(SUM(CAST(t1.amount AS REAL)/1e24), 0) as total
        FROM transactions t1
        WHERE t1.wallet_id = ?
          AND t1.direction = 'in'
          AND t1.counterparty = 'system'
          AND EXISTS (
            SELECT 1 FROM transactions t2 
            WHERE t2.tx_hash = t1.tx_hash 
              AND t2.action_type = 'DELETE_ACCOUNT'
          )
    """, (wallet_id,))
    deleteAccountIn = cur.fetchone()[0]
    print(f"DELETE_ACCOUNT IN: {deleteAccountIn:12.4f} NEAR")
    
    # OUT: exclude self-transfers
    cur.execute("""
        SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0) as total 
        FROM transactions 
        WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
    """, (wallet_id, wallet))
    outSum = cur.fetchone()[0]
    print(f"OUT (excl self):   {outSum:12.4f} NEAR")
    
    # Fees (max per tx_hash)
    cur.execute("""
        SELECT COALESCE(SUM(max_fee), 0) as total FROM (
          SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
          FROM transactions WHERE wallet_id = ? AND direction = 'out' GROUP BY tx_hash
        )
    """, (wallet_id,))
    fees = cur.fetchone()[0]
    print(f"Fees:              {fees:12.6f} NEAR")
    
    # DELETE_ACCOUNT outflows
    cur.execute("""
        SELECT COALESCE(SUM(CAST(t2.amount AS REAL)/1e24), 0) as total
        FROM transactions t1
        JOIN transactions t2 ON t1.tx_hash = t2.tx_hash
        WHERE t1.wallet_id = ?
          AND t1.action_type = 'DELETE_ACCOUNT'
          AND t2.direction = 'in'
          AND t2.counterparty = 'system'
          AND t2.wallet_id != t1.wallet_id
    """, (wallet_id,))
    deleteAccountOutflows = cur.fetchone()[0]
    print(f"DELETE_ACCOUNT out:{deleteAccountOutflows:12.4f} NEAR")
    
    totalIn = inSum + deleteAccountIn
    computed = totalIn - outSum - fees - deleteAccountOutflows
    diff = computed - onChain
    
    print(f"\n--- SUMMARY ---")
    print(f"Total IN:          {totalIn:12.4f} NEAR")
    print(f"Computed:          {computed:12.4f} NEAR")
    print(f"On-chain:          {onChain:12.4f} NEAR")
    print(f"Difference:        {diff:+12.4f} NEAR")

conn.close()
