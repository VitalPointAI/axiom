#!/usr/bin/env python3
"""Analyze CDAO contract transaction patterns to understand fund flows."""

import sqlite3
import requests

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

for wallet in ["vpacademy.cdao.near", "vpointai.cdao.near"]:
    cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
    wallet_id = cur.fetchone()[0]

    print(f"\n{'='*70}")
    print(f"ANALYSIS: {wallet}")
    print(f"{'='*70}")

    # Look at all action types and method names
    cur.execute("""
        SELECT action_type, method_name, direction, COUNT(*),
               SUM(CAST(amount AS REAL))/1e24 as total_near
        FROM transactions
        WHERE wallet_id = ?
        GROUP BY action_type, method_name, direction
        ORDER BY total_near DESC
    """, (wallet_id,))

    print("\nTransaction patterns:")
    print("-" * 70)
    for r in cur.fetchall():
        method = r[1] if r[1] else "N/A"
        print(f"{r[0]:20} {method:25} {r[2]:5} {r[3]:4} txs  {r[4]:12.4f} NEAR")

    # Check counterparties
    print("\nTop counterparties:")
    print("-" * 70)
    cur.execute("""
        SELECT counterparty, direction, COUNT(*),
               SUM(CAST(amount AS REAL))/1e24 as total_near
        FROM transactions
        WHERE wallet_id = ? AND asset = 'NEAR'
        GROUP BY counterparty, direction
        ORDER BY total_near DESC
        LIMIT 15
    """, (wallet_id,))
    for r in cur.fetchall():
        cp = r[0] if r[0] else "self"
        print(f"{cp:40} {r[1]:5} {r[2]:4} txs  {r[3]:12.4f} NEAR")

    # Get RPC balance for comparison
    try:
        resp = requests.post("https://rpc.mainnet.near.org", json={
            "jsonrpc": "2.0", "id": "x",
            "method": "query",
            "params": {"request_type": "view_account", "finality": "final", "account_id": wallet}
        }, timeout=10)
        rpc_balance = int(resp.json()["result"]["amount"]) / 1e24
        print(f"\nRPC Balance: {rpc_balance:.4f} NEAR")
    except Exception as e:
        print(f"\nRPC Error: {e}")

conn.close()
