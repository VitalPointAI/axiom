#!/usr/bin/env python3
"""Quick balance check for all NEAR accounts"""

import json
import requests
import sys
import os
from decimal import Decimal
import base64

NEAR_RPC = "https://free.rpc.fastnear.com"
WALLETS_FILE = os.path.join(os.path.dirname(__file__), "..", "wallets.json")

def get_balance(account_id: str) -> tuple:
    """Returns (liquid_balance, staked_balance, error)"""
    # Liquid balance
    payload = {
        "jsonrpc": "2.0", "id": "1",
        "method": "query",
        "params": {"request_type": "view_account", "finality": "final", "account_id": account_id}
    }
    try:
        resp = requests.post(NEAR_RPC, json=payload, timeout=15)
        data = resp.json()
        if "result" in data:
            liquid = Decimal(data["result"]["amount"]) / Decimal(10**24)
        elif "does not exist" in str(data.get("error", "")):
            return Decimal(0), Decimal(0), "Account does not exist"
        else:
            return None, None, str(data.get("error", "Unknown error"))
    except Exception as e:
        return None, None, str(e)
    
    # Check staked balance in vitalpoint.pool.near
    staked = Decimal(0)
    try:
        payload = {
            "jsonrpc": "2.0", "id": "1",
            "method": "query",
            "params": {
                "request_type": "call_function",
                "finality": "final",
                "account_id": "vitalpoint.pool.near",
                "method_name": "get_account_total_balance",
                "args_base64": base64.b64encode(json.dumps({"account_id": account_id}).encode()).decode()
            }
        }
        resp = requests.post(NEAR_RPC, json=payload, timeout=15)
        data = resp.json()
        if "result" in data and data["result"].get("result"):
            result_bytes = bytes(data["result"]["result"])
            staked = Decimal(result_bytes.decode().strip('"')) / Decimal(10**24)
    except:
        pass
    
    return liquid, staked, None

def main():
    with open(WALLETS_FILE) as f:
        wallets = json.load(f)
    
    accounts = wallets.get("near", [])
    print(f"Checking {len(accounts)} NEAR accounts...\n")
    
    results = []
    total_liquid = Decimal(0)
    total_staked = Decimal(0)
    errors = []
    
    for i, account in enumerate(accounts):
        liquid, staked, error = get_balance(account)
        if error:
            errors.append((account, error))
            print(f"[{i+1}/{len(accounts)}] {account}: ERROR - {error}")
        else:
            total = liquid + staked
            results.append((account, liquid, staked, total))
            if total > 0:
                print(f"[{i+1}/{len(accounts)}] {account}: {liquid:.4f} liquid + {staked:.4f} staked = {total:.4f} NEAR")
            total_liquid += liquid
            total_staked += staked
    
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Accounts checked: {len(accounts)}")
    print(f"Accounts with errors: {len(errors)}")
    print(f"Total liquid NEAR: {total_liquid:.4f}")
    print(f"Total staked NEAR: {total_staked:.4f}")
    print(f"TOTAL NEAR: {total_liquid + total_staked:.4f}")
    
    # Top 10 by balance
    results.sort(key=lambda x: x[3], reverse=True)
    print(f"\nTop 10 accounts:")
    for acc, liq, stk, tot in results[:10]:
        print(f"  {acc}: {tot:.4f} NEAR")
    
    # Save results
    output = {
        "scan_date": __import__('datetime').datetime.utcnow().isoformat(),
        "total_liquid": float(total_liquid),
        "total_staked": float(total_staked),
        "total": float(total_liquid + total_staked),
        "accounts": [{"account": a, "liquid": float(l), "staked": float(s), "total": float(t)} for a, l, s, t in results],
        "errors": [{"account": a, "error": e} for a, e in errors]
    }
    with open("balance_check.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to balance_check.json")

if __name__ == "__main__":
    main()
