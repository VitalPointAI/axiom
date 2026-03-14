#!/usr/bin/env python3
"""
Full Historical Staking Rewards Backfill for ALL Accounts

Processes:
1. vitalpointai.near (wallet 62) - ALL validators
2. aaronluhning.near (wallet 32) - ALL validators
3. aaron.near (wallet 33) - ALL validators
4. db59d3239f2939bb7d8a4a578aceaa8c85ee8e3f.lockup.near (wallet 34) - ALL validators
"""

import json
import logging
import requests
import psycopg2
from datetime import datetime, timezone
from decimal import Decimal, getcontext, InvalidOperation
import time
import traceback

logger = logging.getLogger(__name__)

getcontext().prec = 50

PG_CONN = 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'
NEAR_RPC = 'https://rpc.mainnet.near.org'
CRYPTOCOMPARE_API = 'https://min-api.cryptocompare.com/data'
YOCTO = Decimal('1e24')
EPOCH_DURATION_NS = int(12 * 3600 * 1e9)

# Target accounts to backfill
TARGET_WALLETS = [62, 32, 33, 34]

def get_db():
    return psycopg2.connect(PG_CONN)

def nanoseconds_to_datetime(ns):
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)

def get_near_price_cached(date_str, currency='usd'):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT price FROM price_cache
        WHERE coin_id = 'near' AND date = %s AND currency = %s
    """, (date_str, currency.lower()))

    row = cur.fetchone()
    if row:
        conn.close()
        return Decimal(str(row[0]))

    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        ts = int(dt.timestamp())

        resp = requests.get(f"{CRYPTOCOMPARE_API}/pricehistorical", params={
            'fsym': 'NEAR',
            'tsyms': currency.upper(),
            'ts': ts
        }, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            price = data.get('NEAR', {}).get(currency.upper())
            if price:
                price = Decimal(str(price))
                cur.execute("""
                    INSERT INTO price_cache (coin_id, date, currency, price)
                    VALUES ('near', %s, %s, %s)
                    ON CONFLICT (coin_id, date, currency) DO UPDATE SET price = EXCLUDED.price
                """, (date_str, currency.lower(), float(price)))
                conn.commit()
                conn.close()
                return price
    except Exception as e:
        print(f"  Price fetch error for {date_str}: {e}")

    conn.close()
    return None

def get_exchange_rate(date_str, from_currency='USD', to_currency='CAD'):
    conn = get_db()
    cur = conn.cursor()

    if from_currency.upper() == 'USD' and to_currency.upper() == 'CAD':
        cur.execute("SELECT rate FROM exchange_rate_history WHERE date = %s", (date_str,))
        row = cur.fetchone()
        if row:
            conn.close()
            return Decimal(str(row[0]))

    conn.close()
    return Decimal('1.36')

def get_current_epoch_info():
    resp = requests.post(NEAR_RPC, json={
        'jsonrpc': '2.0', 'id': 1, 'method': 'validators', 'params': [None]
    }, timeout=10)
    data = resp.json()
    return {
        'epoch_height': data['result']['epoch_height'],
        'epoch_start_height': data['result']['epoch_start_height']
    }

def get_staking_history(wallet_id, validator_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT event_type, amount, block_timestamp
        FROM staking_events
        WHERE wallet_id = %s AND validator_id = %s
        ORDER BY block_timestamp
    """, (wallet_id, validator_id))

    events = []
    for row in cur.fetchall():
        events.append({
            'event_type': row[0],
            'amount': Decimal(row[1]) if row[1] else Decimal('0'),
            'timestamp': row[2]
        })

    conn.close()
    return events

def get_current_staked_balance(validator_id, account_id):
    import base64
    args = json.dumps({'account_id': account_id})
    args_b64 = base64.b64encode(args.encode()).decode()

    try:
        resp = requests.post(NEAR_RPC, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'query',
            'params': {
                'request_type': 'call_function',
                'finality': 'final',
                'account_id': validator_id,
                'method_name': 'get_account_staked_balance',
                'args_base64': args_b64
            }
        }, timeout=10)

        data = resp.json()
        if 'result' in data and 'result' in data['result']:
            result_bytes = bytes(data['result']['result'])
            balance_str = result_bytes.decode().strip('"')
            return Decimal(balance_str)
    except Exception as e:
        print(f"  Error getting balance: {e}")
    return Decimal('0')

def get_stnear_balance(account_id):
    """Get stNEAR balance for meta-pool liquid staking"""
    import base64
    args = json.dumps({'account_id': account_id})
    args_b64 = base64.b64encode(args.encode()).decode()

    try:
        resp = requests.post(NEAR_RPC, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'query',
            'params': {
                'request_type': 'call_function',
                'finality': 'final',
                'account_id': 'meta-pool.near',
                'method_name': 'ft_balance_of',
                'args_base64': args_b64
            }
        }, timeout=10)

        data = resp.json()
        if 'result' in data and 'result' in data['result']:
            result_bytes = bytes(data['result']['result'])
            balance_str = result_bytes.decode().strip('"')
            return Decimal(balance_str)
    except Exception as e:
        print(f"  Error getting stNEAR balance: {e}")
    return Decimal('0')

def calculate_epoch_rewards_backfill(wallet_id, account_id, validator_id, current_epoch):
    print(f"\n=== Backfilling {account_id} @ {validator_id} ===")

    events = get_staking_history(wallet_id, validator_id)
    if not events:
        print("  No staking events found")
        return 0, Decimal('0')

    deposit_events = []
    total_deposits = Decimal('0')
    total_withdrawals = Decimal('0')
    first_stake_ts = None

    for event in events:
        if event['event_type'] in ('stake', 'deposit_and_stake'):
            total_deposits += event['amount']
            deposit_events.append((event['timestamp'], event['amount']))
            if first_stake_ts is None:
                first_stake_ts = event['timestamp']
        elif event['event_type'] in ('unstake', 'withdraw', 'withdraw_all'):
            total_withdrawals += event['amount']
            deposit_events.append((event['timestamp'], -event['amount']))

    if first_stake_ts is None:
        print("  No stake events found")
        return 0, Decimal('0')

    print(f"  First stake: {nanoseconds_to_datetime(first_stake_ts).strftime('%Y-%m-%d %H:%M')}")
    print(f"  Total deposited: {total_deposits / YOCTO:.2f} NEAR")
    print(f"  Total withdrawn: {total_withdrawals / YOCTO:.2f} NEAR")

    # Get current balance
    if validator_id == 'meta-pool.near':
        current_balance = get_stnear_balance(account_id)
        print(f"  Current stNEAR balance: {current_balance / YOCTO:.2f}")
    else:
        current_balance = get_current_staked_balance(validator_id, account_id)

    print(f"  Current balance: {current_balance / YOCTO:.2f} NEAR")

    int(datetime.now(timezone.utc).timestamp() * 1e9)
    first_stake_dt = nanoseconds_to_datetime(first_stake_ts)
    now = datetime.now(timezone.utc)
    time_delta = now - first_stake_dt
    num_epochs = int(time_delta.total_seconds() / (12 * 3600))
    first_epoch = current_epoch - num_epochs

    print(f"  Epochs: {first_epoch} to {current_epoch} ({num_epochs} epochs)")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT MIN(epoch_id) FROM staking_epoch_rewards
        WHERE wallet_id = %s AND validator_id = %s
    """, (wallet_id, validator_id))

    existing = cur.fetchone()
    min_existing_epoch = existing[0] if existing[0] else current_epoch + 1
    backfill_to_epoch = min(min_existing_epoch - 1, current_epoch - 1)

    print(f"  Existing epoch data starts at: {min_existing_epoch}")

    if first_epoch >= backfill_to_epoch:
        print("  No epochs to backfill")
        conn.close()
        return 0, Decimal('0')

    num_backfill_epochs = backfill_to_epoch - first_epoch + 1
    print(f"  Will backfill {num_backfill_epochs} epochs ({first_epoch} to {backfill_to_epoch})")

    deposit_events.sort(key=lambda x: x[0])

    epoch_deposits = {}
    for ts, amount in deposit_events:
        time_since_first = ts - first_stake_ts
        epoch_offset = int(time_since_first / EPOCH_DURATION_NS)
        epoch_id = first_epoch + epoch_offset

        if epoch_id not in epoch_deposits:
            epoch_deposits[epoch_id] = Decimal('0')
        epoch_deposits[epoch_id] += amount

    net_deposits = total_deposits - total_withdrawals

    if net_deposits <= 0:
        print("  Net deposits <= 0, position closed")
        conn.close()
        return 0, Decimal('0')

    total_rewards = current_balance - net_deposits
    print(f"  Total rewards earned: {total_rewards / YOCTO:.4f} NEAR")

    if total_rewards <= 0:
        print("  No positive rewards to backfill - using minimum 8% APY estimate")
        implied_rate = Decimal('0.00005')  # ~7.4% APY
    else:
        try:
            implied_rate = (current_balance / net_deposits) ** (Decimal('1') / Decimal(num_epochs)) - 1
            if implied_rate < 0:
                implied_rate = Decimal('0.00005')
        except (InvalidOperation, ZeroDivisionError, ValueError, ArithmeticError) as e:
            logger.warning("Failed to compute implied rate for wallet %s / validator %s: %s", account_id, validator_id, e)
            implied_rate = Decimal('0.00005')

    print(f"  Implied per-epoch rate: {float(implied_rate * 100):.6f}%")
    print(f"  Implied annual APY: {float(((1 + implied_rate) ** 730 - 1) * 100):.2f}%")

    balance = Decimal('0')
    rewards_inserted = 0
    batch_count = 0
    batch_size = 100
    total_reward_near = Decimal('0')

    for epoch_offset in range(num_backfill_epochs):
        epoch_id = first_epoch + epoch_offset

        if epoch_id in epoch_deposits:
            deposit_amount = epoch_deposits[epoch_id]
            balance += deposit_amount
            deposits_this_epoch = deposit_amount
        else:
            deposits_this_epoch = Decimal('0')

        epoch_ts = first_stake_ts + (epoch_offset * EPOCH_DURATION_NS)
        epoch_dt = nanoseconds_to_datetime(epoch_ts)
        epoch_date = epoch_dt.strftime('%Y-%m-%d')

        if balance <= 0:
            continue

        balance_before = balance
        reward_yocto = balance * implied_rate
        balance_after = balance + reward_yocto
        balance = balance_after

        reward_near = reward_yocto / YOCTO
        total_reward_near += reward_near

        price_usd = get_near_price_cached(epoch_date, 'usd')

        if price_usd:
            reward_usd = reward_near * price_usd
            usd_to_cad = get_exchange_rate(epoch_date, 'USD', 'CAD')
            price_cad = price_usd * usd_to_cad
            reward_cad = reward_usd * usd_to_cad
        else:
            price_cad = None
            reward_usd = None
            reward_cad = None

        try:
            cur.execute("""
                INSERT INTO staking_epoch_rewards
                    (wallet_id, validator_id, epoch_id, epoch_timestamp, epoch_date,
                     balance_before, balance_after, deposits, withdrawals,
                     reward_yocto, reward_near, near_price_usd, near_price_cad,
                     reward_usd, reward_cad, calculation_method)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'estimated')
                ON CONFLICT (wallet_id, validator_id, epoch_id) DO NOTHING
            """, (
                wallet_id, validator_id, epoch_id, int(epoch_ts), epoch_date,
                str(int(balance_before)), str(int(balance_after)),
                str(int(deposits_this_epoch)), '0',
                str(int(reward_yocto)), float(reward_near),
                float(price_usd) if price_usd else None,
                float(price_cad) if price_cad else None,
                float(reward_usd) if reward_usd else None,
                float(reward_cad) if reward_cad else None
            ))

            rewards_inserted += 1
            batch_count += 1

            if batch_count >= batch_size:
                conn.commit()
                batch_count = 0
                print(f"  Processed {rewards_inserted}/{num_backfill_epochs} epochs...")
                time.sleep(0.05)

        except Exception as e:
            print(f"  Error inserting epoch {epoch_id}: {e}")
            conn.rollback()

    conn.commit()
    conn.close()
    print(f"  Inserted {rewards_inserted} epoch reward records")
    print(f"  Total rewards calculated: {float(total_reward_near):.4f} NEAR")
    return rewards_inserted, total_reward_near

def get_wallet_validators(wallet_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT validator_id
        FROM staking_events
        WHERE wallet_id = %s AND event_type IN ('stake', 'deposit_and_stake')
        ORDER BY validator_id
    """, (wallet_id,))
    validators = [row[0] for row in cur.fetchall()]
    conn.close()
    return validators

def get_wallet_info(wallet_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT account_id FROM wallets WHERE id = %s", (wallet_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def main():
    print("=" * 60)
    print("FULL HISTORICAL STAKING REWARDS BACKFILL")
    print(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    current_epoch_info = get_current_epoch_info()
    current_epoch = current_epoch_info['epoch_height']
    print(f"Current epoch: {current_epoch}")

    results = {}
    grand_total_records = 0
    grand_total_rewards = Decimal('0')

    for wallet_id in TARGET_WALLETS:
        account_id = get_wallet_info(wallet_id)
        if not account_id:
            print(f"\nWallet {wallet_id} not found")
            continue

        print(f"\n{'='*60}")
        print(f"PROCESSING: {account_id} (wallet {wallet_id})")
        print(f"{'='*60}")

        validators = get_wallet_validators(wallet_id)
        print(f"Found {len(validators)} validators")

        wallet_records = 0
        wallet_rewards = Decimal('0')

        for validator_id in validators:
            try:
                records, rewards = calculate_epoch_rewards_backfill(
                    wallet_id, account_id, validator_id, current_epoch
                )
                wallet_records += records
                wallet_rewards += rewards
            except Exception as e:
                print(f"  ERROR processing {validator_id}: {e}")
                traceback.print_exc()

        results[account_id] = {
            'records': wallet_records,
            'rewards_near': float(wallet_rewards)
        }
        grand_total_records += wallet_records
        grand_total_rewards += wallet_rewards

        print(f"\n{account_id} COMPLETE:")
        print(f"  Total records: {wallet_records}")
        print(f"  Total rewards: {float(wallet_rewards):.4f} NEAR")

    # Final summary
    print("\n" + "=" * 60)
    print("BACKFILL COMPLETE")
    print(f"Finished: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    print("\nSUMMARY BY ACCOUNT:")
    for account, data in results.items():
        print(f"  {account}: {data['records']} records, {data['rewards_near']:.4f} NEAR")

    print("\nGRAND TOTALS:")
    print(f"  Total records inserted: {grand_total_records}")
    print(f"  Total rewards: {float(grand_total_rewards):.4f} NEAR")

    # Query actual totals from database
    conn = get_db()
    cur = conn.cursor()

    print("\nVERIFICATION FROM DATABASE:")
    for wallet_id in TARGET_WALLETS:
        account_id = get_wallet_info(wallet_id)
        if not account_id:
            continue
        cur.execute("""
            SELECT validator_id, COUNT(*) as cnt, SUM(reward_near) as total_near,
                   SUM(reward_usd) as total_usd, MIN(epoch_date) as first, MAX(epoch_date) as last
            FROM staking_epoch_rewards
            WHERE wallet_id = %s
            GROUP BY validator_id
            ORDER BY validator_id
        """, (wallet_id,))

        print(f"\n  {account_id}:")
        for row in cur.fetchall():
            print(f"    {row[0]}: {row[1]} epochs, {row[2]:.4f} NEAR, ${row[3] or 0:.2f} USD ({row[4]} to {row[5]})")

    conn.close()

if __name__ == '__main__':
    main()
