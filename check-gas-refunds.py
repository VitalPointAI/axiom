#!/usr/bin/env python3
"""Check for gas refunds in CDAO transactions."""
import sqlite3
import requests

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

wallet = "vpacademy.cdao.near"
cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
wallet_id = cur.fetchone()[0]

print(f"Checking gas refunds for {wallet}")
print("="*70)

# Get sample transactions to check for refund receipts
cur.execute("""
    SELECT DISTINCT tx_hash 
    FROM transactions 
    WHERE wallet_id = ? AND direction = 'out'
    LIMIT 5
""", (wallet_id,))
sample_hashes = [r[0] for r in cur.fetchall()]

print("\nChecking RPC for refund receipts in sample transactions:")
print("-"*70)

for tx_hash in sample_hashes:
    try:
        resp = requests.post("https://rpc.mainnet.near.org", json={
            "jsonrpc": "2.0", "id": "1",
            "method": "EXPERIMENTAL_tx_status",
            "params": {
                "tx_hash": tx_hash,
                "sender_account_id": wallet,
                "wait_until": "FINAL"
            }
        }, timeout=15)
        result = resp.json().get("result", {})
        
        # Look for receipts that are refunds
        receipts = result.get("receipts", [])
        receipts_outcome = result.get("receipts_outcome", [])
        
        for ro in receipts_outcome:
            outcome = ro.get("outcome", {})
            executor = outcome.get("executor_id", "")
            
            # Check if there's a transfer back to the wallet (refund)
            for action in outcome.get("receipt_ids", []):
                pass  # Just looking at structure
            
        # Check final execution outcome for gas refund
        final_outcome = result.get("transaction_outcome", {}).get("outcome", {})
        gas_burnt = final_outcome.get("gas_burnt", 0)
        tokens_burnt = int(final_outcome.get("tokens_burnt", "0"))
        
        print(f"\n{tx_hash[:20]}...")
        print(f"  Gas burnt: {gas_burnt}")
        print(f"  Tokens burnt: {tokens_burnt / 1e24:.6f} NEAR")
        print(f"  Receipts: {len(receipts_outcome)}")
        
    except Exception as e:
        print(f"\n{tx_hash[:20]}... Error: {e}")

# Now let's check what direction='in' from 'system' counterparty we have
print("\n\nChecking system-originated IN transactions:")
print("-"*70)
cur.execute("""
    SELECT action_type, counterparty, COUNT(*), SUM(CAST(amount AS REAL)/1e24)
    FROM transactions
    WHERE wallet_id = ? AND direction = 'in' 
    GROUP BY action_type, counterparty
    HAVING counterparty LIKE '%system%' OR counterparty IS NULL OR counterparty = ''
""", (wallet_id,))
for r in cur.fetchall():
    print(f"  {r[0]:20} {r[1] or 'NULL':20} {r[2]:4} txs  {r[3] or 0:10.4f} NEAR")

# Check how the indexer handles receipts
print("\n\nChecking raw_json for refund patterns:")
print("-"*70)
cur.execute("""
    SELECT tx_hash, raw_json
    FROM transactions
    WHERE wallet_id = ? AND direction = 'in' AND raw_json LIKE '%refund%'
    LIMIT 3
""", (wallet_id,))
for r in cur.fetchall():
    print(f"  {r[0][:20]}... has 'refund' in raw_json")

conn.close()
