#!/usr/bin/env python3
"""Fix staking positions by querying actual on-chain staking balances."""

import sqlite3
import requests
import json
import base64

NEAR_RPC = "https://rpc.fastnear.com"
DB_PATH = "/home/deploy/neartax/neartax.db"

def get_staked_balance(account, pool):
    """Query staking pool for account's staked balance."""
    try:
        args = base64.b64encode(json.dumps({"account_id": account}).encode()).decode()
        payload = {
            "jsonrpc": "2.0", "id": "1", "method": "query",
            "params": {
                "request_type": "call_function", "finality": "final",
                "account_id": pool, "method_name": "get_account_staked_balance",
                "args_base64": args
            }
        }
        r = requests.post(NEAR_RPC, json=payload, timeout=10)
        if r.status_code == 200:
            result = r.json().get("result", {}).get("result", [])
            if result:
                value = bytes(result).decode().strip('"')
                return int(value)
    except Exception as e:
        print(f"    Error querying {pool}: {e}")
    return 0

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get all NEAR wallets for user 1
    c.execute("SELECT w.id, w.account_id FROM wallets w WHERE w.user_id = 1 AND w.chain = 'NEAR'")
    wallets = c.fetchall()

    # Known staking pools to check
    pools = [
        "vitalpoint.pool.near",
        "zavodil.poolv1.near",
        "epic.poolv1.near",
        "openshards.poolv1.near",
        "astro-stakers.poolv1.near",
        "01node.poolv1.near",
        "chorus-one.poolv1.near",
        "dokiacapital.poolv1.near",
        "staked.poolv1.near",
    ]

    print(f"Checking {len(wallets)} wallets against {len(pools)} staking pools...")
    print()
    
    total_staked = 0
    updates = []

    for wid, account in wallets:
        account_total = 0
        for pool in pools:
            staked = get_staked_balance(account, pool)
            if staked > 1e20:  # More than 0.0001 NEAR
                staked_near = staked / 1e24
                print(f"  {account} -> {pool}: {staked_near:.2f} NEAR")
                total_staked += staked_near
                account_total += staked_near
                updates.append((wid, pool, str(staked)))
        
        if account_total > 0:
            print(f"  {account} TOTAL: {account_total:.2f} NEAR")
            print()

    # Clear old staking positions and insert fresh data
    c.execute("DELETE FROM staking_positions WHERE wallet_id IN (SELECT id FROM wallets WHERE user_id = 1)")
    print("Cleared old staking positions")

    # Insert new positions
    for wid, pool, amount in updates:
        c.execute("INSERT INTO staking_positions (wallet_id, validator, staked_amount) VALUES (?, ?, ?)", 
                 (wid, pool, amount))
    
    conn.commit()
    print(f"\nInserted {len(updates)} staking positions")
    print(f"Total staked: {total_staked:.2f} NEAR")
    
    conn.close()

if __name__ == "__main__":
    main()
