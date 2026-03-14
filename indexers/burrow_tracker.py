#!/usr/bin/env python3
"""Burrow Lending Protocol Position Tracker

Decimal handling (CORRECTED):
- Supply/Borrow: All balances appear to use 12 extra decimals for sub-18-decimal tokens
  For tokens < 18 decimals: divide by 10^12 (NOT 10^extra_decimals from config!)
  For tokens >= 18 decimals: divide by 10^native
- Collateral: Always stored at 18 decimals (divide by 10^18)
  EXCEPT for 24-decimal tokens which use 24 decimals
"""

import json
import base64
import requests
import psycopg2

PG_CONN = 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'
BURROW_CONTRACT = 'contract.main.burrow.near'
RPC_URL = 'https://rpc.fastnear.com'

# Native token decimals
TOKEN_DECIMALS = {
    'wrap.near': 24,
    'lst.rhealab.near': 24,
    'meta-pool.near': 24,
    'xtoken.rhealab.near': 18,
    'aurora': 18,
    '17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1': 6,
    'a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.factory.bridge.near': 6,
    'dac17f958d2ee523a2206206994597c13d831ec7.factory.bridge.near': 6,
    '6b175474e89094c44da98b954eedeac495271d0f.factory.bridge.near': 18,
    'zec.omft.near': 8,
}

TOKEN_SYMBOLS = {
    'wrap.near': 'wNEAR',
    'zec.omft.near': 'ZEC',
    'lst.rhealab.near': 'rNEAR',
    'xtoken.rhealab.near': 'xRHEA',
    'meta-pool.near': 'STNEAR',
    'aurora': 'ETH',
    '17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1': 'USDC',
    'a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.factory.bridge.near': 'USDC.e',
    'dac17f958d2ee523a2206206994597c13d831ec7.factory.bridge.near': 'USDT.e',
    '6b175474e89094c44da98b954eedeac495271d0f.factory.bridge.near': 'DAI',
}

def get_symbol(token_id):
    return TOKEN_SYMBOLS.get(token_id, token_id.split('.')[0].upper())

def convert_supply_borrow_balance(balance, token_id):
    """Convert supplied/borrowed balance to actual amount.

    Based on observed data, Burrow uses:
    - 12 extra decimal places for all sub-18-decimal tokens
    - Native decimals for 18+ decimal tokens
    """
    native_decimals = TOKEN_DECIMALS.get(token_id, 18)

    if native_decimals >= 18:
        # For 18+ decimal tokens, stored at native decimals
        return balance / (10 ** native_decimals)
    else:
        # For < 18 decimal tokens, Burrow uses 12 extra decimals
        # This is empirically determined - NOT the config's extra_decimals value!
        return balance / (10 ** 12)

def convert_collateral_balance(balance, token_id):
    """Convert collateral balance to actual amount.

    Collateral is stored at 18 decimals for most tokens,
    except 24-decimal tokens which use 24 decimals.
    """
    native_decimals = TOKEN_DECIMALS.get(token_id, 18)

    if native_decimals >= 24:
        return balance / (10 ** 24)
    else:
        return balance / (10 ** 18)

def get_burrow_account(account_id):
    try:
        args = json.dumps({"account_id": account_id})
        args_b64 = base64.b64encode(args.encode()).decode()

        resp = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": "1", "method": "query",
            "params": {
                "request_type": "call_function",
                "finality": "final",
                "account_id": BURROW_CONTRACT,
                "method_name": "get_account",
                "args_base64": args_b64
            }
        }, timeout=10)

        if resp.ok:
            result = resp.json().get("result", {}).get("result")
            if result:
                return json.loads(bytes(result).decode())
    except Exception as e:
        print(f"Error fetching {account_id}: {e}")
    return None


def sync_burrow_positions(user_id=None):
    conn = psycopg2.connect(PG_CONN)
    cursor = conn.cursor()

    if user_id:
        cursor.execute("SELECT id, account_id FROM wallets WHERE user_id = %s AND chain = 'NEAR'", (user_id,))
    else:
        cursor.execute("SELECT id, account_id FROM wallets WHERE chain = 'NEAR'")
    wallets = cursor.fetchall()

    wallet_ids = [w[0] for w in wallets]
    if wallet_ids:
        cursor.execute("DELETE FROM defi_events WHERE wallet_id = ANY(%s) AND protocol = 'burrow'", (wallet_ids,))

    print(f"Syncing Burrow for {len(wallets)} wallets...")
    total = 0

    for wallet_id, account_id in wallets:
        data = get_burrow_account(account_id)
        if not data:
            continue

        # Supply positions
        for pos in data.get('supplied', []):
            token_id = pos['token_id']
            balance = int(pos['balance'])
            symbol = get_symbol(token_id)
            amount = convert_supply_borrow_balance(balance, token_id)

            if amount >= 0.0001:
                cursor.execute("""
                    INSERT INTO defi_events
                        (wallet_id, protocol, event_type, token_contract, token_symbol,
                         amount, amount_decimal, counterparty, block_timestamp)
                    VALUES (%s, 'burrow', 'supply', %s, %s, %s, %s, 'contract.main.burrow.near',
                            EXTRACT(EPOCH FROM NOW())::BIGINT * 1000000000)
                """, (wallet_id, token_id, symbol, str(amount), amount))
                print(f"  {account_id}: Supply {amount:.4f} {symbol}")
                total += 1

        # Collateral positions - use different decimal conversion
        for pos in data.get('collateral', []):
            token_id = pos['token_id']
            balance = int(pos['balance'])
            symbol = get_symbol(token_id)
            amount = convert_collateral_balance(balance, token_id)

            if amount >= 0.0001:
                cursor.execute("""
                    INSERT INTO defi_events
                        (wallet_id, protocol, event_type, token_contract, token_symbol,
                         amount, amount_decimal, counterparty, block_timestamp)
                    VALUES (%s, 'burrow', 'collateral', %s, %s, %s, %s, 'contract.main.burrow.near',
                            EXTRACT(EPOCH FROM NOW())::BIGINT * 1000000000)
                """, (wallet_id, token_id, symbol, str(amount), amount))
                print(f"  {account_id}: Collateral {amount:.4f} {symbol}")
                total += 1

        # Borrowed positions
        for pos in data.get('borrowed', []):
            token_id = pos['token_id']
            balance = int(pos['balance'])
            symbol = get_symbol(token_id)
            amount = convert_supply_borrow_balance(balance, token_id)

            if amount >= 0.0001:
                cursor.execute("""
                    INSERT INTO defi_events
                        (wallet_id, protocol, event_type, token_contract, token_symbol,
                         amount, amount_decimal, counterparty, block_timestamp)
                    VALUES (%s, 'burrow', 'borrow', %s, %s, %s, %s, 'contract.main.burrow.near',
                            EXTRACT(EPOCH FROM NOW())::BIGINT * 1000000000)
                """, (wallet_id, token_id, symbol, str(amount), amount))
                print(f"  {account_id}: Borrow {amount:.4f} {symbol}")
                total += 1

    conn.commit()
    conn.close()
    print(f"\nDone! {total} positions.")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', type=int)
    args = parser.parse_args()
    sync_burrow_positions(args.user)
