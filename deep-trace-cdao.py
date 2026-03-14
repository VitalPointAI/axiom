#!/usr/bin/env python3
"""Deep trace of CDAO wallet balance calculation."""
import sqlite3
import requests

with sqlite3.connect("neartax.db") as conn:
    cur = conn.cursor()
    try:
        wallet = "vpacademy.cdao.near"
        cur.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,))
        wallet_id = cur.fetchone()[0]

        print(f"{'='*70}")
        print(f"BALANCE RECONCILIATION: {wallet}")
        print(f"{'='*70}")

        # Get RPC balance
        resp = requests.post("https://rpc.fastnear.com", json={
            "jsonrpc": "2.0", "id": "verify",
            "method": "query",
            "params": {"request_type": "view_account", "finality": "final", "account_id": wallet}
        }, timeout=10)
        result = resp.json().get("result", {})
        rpc_balance = float(result.get("amount", 0)) / 1e24
        storage_bytes = result.get("storage_usage", 0)
        storage_cost = storage_bytes * 1e-5

        print("\nRPC State:")
        print(f"  Available balance: {rpc_balance:12.4f} NEAR")
        print(f"  Storage ({storage_bytes:,} bytes): {storage_cost:12.4f} NEAR (locked)")
        print(f"  Total in account:  {rpc_balance + storage_cost:12.4f} NEAR")

        # Trace all IN by action type
        print("\n--- INFLOWS ---")
        cur.execute("""
            SELECT action_type, method_name, counterparty,
                   SUM(CAST(amount AS REAL)/1e24) as total,
                   COUNT(*) as cnt
            FROM transactions
            WHERE wallet_id = ? AND direction = 'in'
            GROUP BY action_type, method_name, counterparty
            ORDER BY total DESC
        """, (wallet_id,))
        total_in = 0
        for r in cur.fetchall():
            action, method, cp, amt, cnt = r
            method = method or "-"
            cp = cp or "self"
            is_self = "(SELF)" if cp == wallet else ""
            print(f"  {action:15} {method:25} {cp[:20]:20} {amt:10.4f} NEAR ({cnt:3} txs) {is_self}")
            if cp != wallet:  # Exclude self
                total_in += amt

        print(f"\n  Total IN (excl self): {total_in:12.4f} NEAR")

        # Trace all OUT by counterparty
        print("\n--- OUTFLOWS ---")
        cur.execute("""
            SELECT counterparty,
                   SUM(CAST(amount AS REAL)/1e24) as total,
                   COUNT(*) as cnt
            FROM transactions
            WHERE wallet_id = ? AND direction = 'out'
            GROUP BY counterparty
            ORDER BY total DESC
        """, (wallet_id,))
        total_out = 0
        total_self_out = 0
        for r in cur.fetchall():
            cp, amt, cnt = r
            cp = cp or "unknown"
            is_self = "(SELF)" if cp == wallet else ""
            print(f"  {cp:45} {amt:10.4f} NEAR ({cnt:3} txs) {is_self}")
            if cp == wallet:
                total_self_out += amt
            else:
                total_out += amt

        print(f"\n  Total OUT (excl self): {total_out:12.4f} NEAR")
        print(f"  Self-transfers:        {total_self_out:12.4f} NEAR (excluded)")

        # Fees - get unique per tx_hash
        cur.execute("""
            SELECT SUM(max_fee) FROM (
                SELECT MAX(CAST(fee AS REAL)/1e24) as max_fee
                FROM transactions WHERE wallet_id = ? AND direction = 'out'
                GROUP BY tx_hash
            )
        """, (wallet_id,))
        total_fees = cur.fetchone()[0] or 0
        print("\n--- FEES ---")
        print(f"  Total fees (unique per tx): {total_fees:12.6f} NEAR")

        # Calculate
        computed = total_in - total_out - total_fees
        diff = computed - rpc_balance

        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        print(f"  IN (excl self):    {total_in:12.4f} NEAR")
        print(f"  OUT (excl self):  -{total_out:12.4f} NEAR")
        print(f"  Fees:             -{total_fees:12.6f} NEAR")
        print("  ─────────────────────────────────────")
        print(f"  Computed:          {computed:12.4f} NEAR")
        print(f"  RPC balance:       {rpc_balance:12.4f} NEAR")
        print(f"  DIFFERENCE:        {diff:+12.4f} NEAR")
        print(f"\n  Storage locked:    {storage_cost:12.4f} NEAR")
        print(f"  Diff + storage:    {diff + storage_cost:+12.4f} NEAR")

        # If diff is negative, we're missing IN
        if diff < 0:
            print(f"\n  ⚠️  We are MISSING {abs(diff):.4f} NEAR in recorded inflows")
        else:
            print(f"\n  ⚠️  We have EXTRA {diff:.4f} NEAR in recorded inflows")
    finally:
        cur.close()
