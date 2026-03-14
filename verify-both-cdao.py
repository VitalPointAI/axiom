#!/usr/bin/env python3
import sqlite3
import requests

conn = sqlite3.connect("neartax.db")
cur = conn.cursor()

for wallet in ["vpacademy.cdao.near", "vpointai.cdao.near"]:
    cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
    wallet_id = cur.fetchone()[0]

    # IN
    cur.execute("""
        SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0)
        FROM transactions WHERE wallet_id = ? AND direction = 'in' AND counterparty != ?
    """, (wallet_id, wallet))
    total_in = cur.fetchone()[0]

    # OUT
    cur.execute("""
        SELECT COALESCE(SUM(CAST(amount AS REAL)/1e24), 0)
        FROM transactions WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
    """, (wallet_id, wallet))
    total_out = cur.fetchone()[0]

    # NEW fees (excluding self-transfers)
    cur.execute("""
        SELECT COALESCE(SUM(max_fee), 0) FROM (
            SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
            FROM transactions
            WHERE wallet_id = ? AND direction = 'out' AND counterparty != ?
            GROUP BY tx_hash
        )
    """, (wallet_id, wallet))
    fees = cur.fetchone()[0]

    # RPC
    resp = requests.post("https://rpc.fastnear.com", json={
        "jsonrpc": "2.0", "id": "verify", "method": "query",
        "params": {"request_type": "view_account", "finality": "final", "account_id": wallet}
    }, timeout=10)
    rpc_balance = float(resp.json().get("result", {}).get("amount", 0)) / 1e24

    computed = total_in - total_out - fees
    diff = computed - rpc_balance
    diff_cad = diff * 4.5

    within = "✅" if abs(diff_cad) < 5 else "❌"

    print(f"{wallet}:")
    print(f"  Computed: {computed:.4f} NEAR | RPC: {rpc_balance:.4f} NEAR")
    print(f"  Diff: {diff:+.4f} NEAR (~${diff_cad:+.2f} CAD) {within}")
    print()

conn.close()
