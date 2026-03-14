#!/usr/bin/env python3
"""
Epoch Staking Balance Snapshot Indexer

Takes snapshots of staked balances at each epoch boundary.
Run this via cron every 12 hours (epoch duration).

Calculates real rewards as: current_balance - previous_balance - deposits + withdrawals
"""

import requests
import psycopg2
import json
import base64
from datetime import datetime

PG_CONN = 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'
NEAR_RPC = 'https://rpc.fastnear.com'


def get_current_epoch():
    """Get current epoch info from NEAR RPC."""
    try:
        resp = requests.post(NEAR_RPC, json={
            'jsonrpc': '2.0',
            'id': '1',
            'method': 'validators',
            'params': [None]
        }, timeout=30)
        data = resp.json()
        result = data.get('result', {})
        return {
            'epoch_id': result.get('epoch_height'),
            'epoch_start_height': result.get('epoch_start_height'),
        }
    except Exception as e:
        print(f'Error getting epoch: {e}')
        return None


def get_staked_balance(account_id: str, pool_id: str) -> tuple:
    """Query staked and unstaked balance from pool contract."""
    try:
        args = json.dumps({'account_id': account_id})
        args_b64 = base64.b64encode(args.encode()).decode()

        resp = requests.post(NEAR_RPC, json={
            'jsonrpc': '2.0',
            'id': '1',
            'method': 'query',
            'params': {
                'request_type': 'call_function',
                'finality': 'final',
                'account_id': pool_id,
                'method_name': 'get_account',
                'args_base64': args_b64
            }
        }, timeout=30)

        data = resp.json()
        if 'result' in data and 'result' in data['result']:
            result_bytes = bytes(data['result']['result'])
            result = json.loads(result_bytes.decode())
            return (
                result.get('staked_balance', '0'),
                result.get('unstaked_balance', '0')
            )
    except Exception as e:
        print(f'  Error querying {pool_id} for {account_id}: {e}')
    return ('0', '0')


def take_snapshots():
    """Take balance snapshots for all active staking positions."""
    # Get current epoch
    epoch_info = get_current_epoch()
    if not epoch_info:
        print('Failed to get epoch info')
        return

    epoch_id = epoch_info['epoch_id']
    epoch_ts = int(datetime.utcnow().timestamp() * 1e9)  # nanoseconds

    print(f'Taking snapshots for epoch {epoch_id}')

    conn = psycopg2.connect(PG_CONN)
    cur = conn.cursor()

    # Get all active staking positions (users with stake > 0)
    cur.execute("""
        SELECT DISTINCT sp.wallet_id, w.account_id, sp.validator
        FROM staking_positions sp
        JOIN wallets w ON sp.wallet_id = w.id
        WHERE CAST(sp.staked_amount AS NUMERIC) > 0
        ORDER BY sp.wallet_id
    """)
    positions = cur.fetchall()

    print(f'Found {len(positions)} active staking positions')

    snapshots_taken = 0
    skipped = 0

    for wallet_id, account_id, validator in positions:
        # Check if we already have a snapshot for this epoch
        cur.execute("""
            SELECT id FROM staking_balance_snapshots
            WHERE wallet_id = %s AND validator_id = %s AND epoch_id = %s
        """, (wallet_id, validator, epoch_id))

        if cur.fetchone():
            skipped += 1
            continue

        # Get current balance from pool
        staked, unstaked = get_staked_balance(account_id, validator)

        if staked == '0' and unstaked == '0':
            continue

        # Insert snapshot
        try:
            cur.execute("""
                INSERT INTO staking_balance_snapshots
                    (wallet_id, validator_id, epoch_id, epoch_timestamp, staked_balance, unstaked_balance)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (wallet_id, validator_id, epoch_id) DO NOTHING
            """, (wallet_id, validator, epoch_id, epoch_ts, staked, unstaked))
            conn.commit()

            staked_near = int(staked) / 1e24
            print(f'  {account_id} @ {validator}: {staked_near:.4f} NEAR')
            snapshots_taken += 1

        except Exception as e:
            print(f'  Error saving snapshot: {e}')
            conn.rollback()

    conn.close()

    print(f'\nDone! Snapshots: {snapshots_taken}, Skipped (already exists): {skipped}')


if __name__ == '__main__':
    take_snapshots()
