#!/usr/bin/env python3
"""SWEAT Jars Position Tracker

Tracks SWEAT staked in Jars (v2.jars.sweat contract).
"""

import json
import base64
import requests
import psycopg2

PG_CONN = 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'
JARS_CONTRACT = 'v2.jars.sweat'
RPC_URL = 'https://rpc.fastnear.com'


def get_jars_for_account(account_id):
    """Get SWEAT Jars positions for an account."""
    try:
        args = json.dumps({"account_id": account_id})
        args_b64 = base64.b64encode(args.encode()).decode()

        resp = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": "1", "method": "query",
            "params": {
                "request_type": "call_function",
                "finality": "final",
                "account_id": JARS_CONTRACT,
                "method_name": "get_jars_for_account",
                "args_base64": args_b64
            }
        }, timeout=10)

        if resp.ok:
            result = resp.json().get("result", {}).get("result")
            if result:
                data = json.loads(bytes(result).decode())
                return data
    except Exception as e:
        print(f"Error fetching jars for {account_id}: {e}")
    return None


def sync_sweat_jars(user_id=None):
    conn = psycopg2.connect(PG_CONN)
    cursor = conn.cursor()

    if user_id:
        cursor.execute("SELECT id, account_id FROM wallets WHERE user_id = %s AND chain = 'NEAR'", (user_id,))
    else:
        cursor.execute("SELECT id, account_id FROM wallets WHERE chain = 'NEAR'")
    wallets = cursor.fetchall()

    # Clear old SWEAT Jars positions
    wallet_ids = [w[0] for w in wallets]
    if wallet_ids:
        cursor.execute("DELETE FROM defi_events WHERE wallet_id = ANY(%s) AND protocol = 'sweat_jars'", (wallet_ids,))

    print(f"Syncing SWEAT Jars for {len(wallets)} wallets...")
    total = 0

    for wallet_id, account_id in wallets:
        data = get_jars_for_account(account_id)
        if not data:
            continue

        # Sum all jars for this account
        total_jars_amount = 0
        jar_details = []

        for jar_type, positions in data.items():
            for pos in positions:
                # pos is [timestamp, amount]
                if len(pos) >= 2:
                    amount = int(pos[1]) / 1e18  # SWEAT has 18 decimals
                    total_jars_amount += amount
                    jar_details.append(f"{jar_type}: {amount:.2f}")

        if total_jars_amount >= 0.01:
            cursor.execute("""
                INSERT INTO defi_events
                    (wallet_id, protocol, event_type, token_contract, token_symbol,
                     amount, amount_decimal, counterparty, block_timestamp, tax_notes)
                VALUES (%s, 'sweat_jars', 'staking', 'token.sweat', 'SWEAT',
                        %s, %s, 'v2.jars.sweat',
                        EXTRACT(EPOCH FROM NOW())::BIGINT * 1000000000, %s)
            """, (wallet_id, str(total_jars_amount), total_jars_amount, '; '.join(jar_details)))
            print(f"  {account_id}: {total_jars_amount:.2f} SWEAT in Jars")
            total += 1

    conn.commit()
    conn.close()
    print(f"\nDone! {total} Jars positions.")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', type=int)
    args = parser.parse_args()
    sync_sweat_jars(args.user)
