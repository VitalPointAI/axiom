#!/usr/bin/env python3
"""
Epoch Staking Rewards Indexer

Calculates per-epoch staking rewards from balance snapshots.
Run after epoch_staking_snapshot.py to calculate rewards for the latest epoch.

Reward formula: reward = current_balance - previous_balance - deposits + withdrawals
"""

import os
import json
import base64
import requests
import psycopg2
from datetime import datetime, timezone
from decimal import Decimal

PG_CONN = os.environ.get('DATABASE_URL',
    'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax')
NEAR_RPC = 'https://rpc.fastnear.com'
CRYPTOCOMPARE_API = 'https://min-api.cryptocompare.com/data'
YOCTO = Decimal('1e24')


def get_db():
    """Get database connection."""
    return psycopg2.connect(PG_CONN)


def epoch_timestamp_to_date(epoch_ts: int) -> str:
    """Convert epoch nanosecond timestamp to date string (YYYY-MM-DD)."""
    if not epoch_ts:
        return None
    # Convert nanoseconds to seconds
    ts_seconds = epoch_ts / 1e9
    dt = datetime.fromtimestamp(ts_seconds, tz=timezone.utc)
    return dt.strftime('%Y-%m-%d')


def get_near_price(date_str: str, currency: str = 'usd') -> Decimal:
    """Get NEAR price for a specific date from CryptoCompare or cache."""
    conn = get_db()
    cur = conn.cursor()

    # Check cache first
    cur.execute("""
        SELECT price FROM price_cache
        WHERE coin_id = 'near' AND date = %s AND currency = %s
    """, (date_str, currency.lower()))

    row = cur.fetchone()
    if row:
        conn.close()
        return Decimal(str(row[0]))

    # Fetch from CryptoCompare
    try:
        # Parse date and convert to timestamp
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

                # Cache the price
                cur.execute("""
                    INSERT INTO price_cache (coin_id, date, currency, price)
                    VALUES ('near', %s, %s, %s)
                    ON CONFLICT (coin_id, date, currency) DO UPDATE SET price = EXCLUDED.price
                """, (date_str, currency.lower(), float(price)))
                conn.commit()
                conn.close()
                return price
    except Exception as e:
        print(f"  Error fetching price for {date_str}: {e}")

    conn.close()
    return None


def get_exchange_rate(date_str: str, from_currency: str = 'USD', to_currency: str = 'CAD') -> Decimal:
    """Get exchange rate for converting between currencies."""
    conn = get_db()
    cur = conn.cursor()

    # Check exchange_rate_history (simple table, assumes USD/CAD)
    if from_currency.upper() == 'USD' and to_currency.upper() == 'CAD':
        cur.execute("""
            SELECT rate FROM exchange_rate_history
            WHERE date = %s
        """, (date_str,))

        row = cur.fetchone()
        if row:
            conn.close()
            return Decimal(str(row[0]))

    # Check exchange_rates table
    cur.execute("""
        SELECT rate FROM exchange_rates
        WHERE from_currency = %s AND to_currency = %s AND date = %s
    """, (from_currency.upper(), to_currency.upper(), date_str))

    row = cur.fetchone()
    if row:
        conn.close()
        return Decimal(str(row[0]))

    # Try to find the closest rate
    cur.execute("""
        SELECT rate FROM exchange_rates
        WHERE from_currency = %s AND to_currency = %s
        ORDER BY date DESC LIMIT 1
    """, (from_currency.upper(), to_currency.upper()))

    row = cur.fetchone()
    conn.close()
    if row:
        return Decimal(str(row[0]))

    # Default fallback
    return Decimal('1.36')  # Approximate USD to CAD


def get_staking_events_for_epoch(wallet_id: int, validator_id: str, epoch_start_ts: int, epoch_end_ts: int):
    """Get deposits and withdrawals that occurred during an epoch."""
    conn = get_db()
    cur = conn.cursor()

    deposits = Decimal('0')
    withdrawals = Decimal('0')

    # Query staking events within the epoch timeframe
    cur.execute("""
        SELECT event_type, amount, block_timestamp
        FROM staking_events
        WHERE wallet_id = %s
        AND validator_id = %s
        AND block_timestamp >= %s
        AND block_timestamp < %s
    """, (wallet_id, validator_id, epoch_start_ts, epoch_end_ts))

    for row in cur.fetchall():
        event_type = row[0]
        amount = Decimal(row[1]) if row[1] else Decimal('0')

        if event_type in ('stake', 'deposit_and_stake'):
            deposits += amount
        elif event_type in ('unstake', 'withdraw', 'withdraw_all'):
            withdrawals += amount

    conn.close()
    return deposits, withdrawals


def calculate_rewards_for_epoch(epoch_id: int):
    """Calculate rewards for all wallets/validators for a specific epoch."""
    conn = get_db()
    cur = conn.cursor()

    # Get snapshots for this epoch
    cur.execute("""
        SELECT s.wallet_id, s.validator_id, s.staked_balance, s.epoch_timestamp,
               w.account_id
        FROM staking_balance_snapshots s
        JOIN wallets w ON s.wallet_id = w.id
        WHERE s.epoch_id = %s
    """, (epoch_id,))

    current_snapshots = cur.fetchall()

    if not current_snapshots:
        print(f"No snapshots found for epoch {epoch_id}")
        conn.close()
        return 0

    # Get the previous epoch ID
    cur.execute("""
        SELECT DISTINCT epoch_id FROM staking_balance_snapshots
        WHERE epoch_id < %s
        ORDER BY epoch_id DESC LIMIT 1
    """, (epoch_id,))

    prev_row = cur.fetchone()
    prev_epoch_id = prev_row[0] if prev_row else None

    if not prev_epoch_id:
        print(f"No previous epoch found for {epoch_id}, cannot calculate rewards")
        conn.close()
        return 0

    rewards_calculated = 0

    for wallet_id, validator_id, current_balance, epoch_ts, account_id in current_snapshots:
        current_balance = Decimal(current_balance)

        # Check if we already calculated this reward
        cur.execute("""
            SELECT id FROM staking_epoch_rewards
            WHERE wallet_id = %s AND validator_id = %s AND epoch_id = %s
        """, (wallet_id, validator_id, epoch_id))

        if cur.fetchone():
            continue

        # Get previous epoch balance
        cur.execute("""
            SELECT staked_balance, epoch_timestamp FROM staking_balance_snapshots
            WHERE wallet_id = %s AND validator_id = %s AND epoch_id = %s
        """, (wallet_id, validator_id, prev_epoch_id))

        prev_row = cur.fetchone()
        if not prev_row:
            # No previous balance, this might be a new staking position
            # Treat previous balance as 0
            prev_balance = Decimal('0')
            prev_ts = epoch_ts - 43200 * 1e9  # ~12 hours earlier
        else:
            prev_balance = Decimal(prev_row[0])
            prev_ts = prev_row[1]

        # Get deposits and withdrawals during this epoch
        deposits, withdrawals = get_staking_events_for_epoch(
            wallet_id, validator_id, prev_ts, epoch_ts
        )

        # Calculate reward: current - previous - deposits + withdrawals
        reward_yocto = current_balance - prev_balance - deposits + withdrawals

        # If negative reward (shouldn't happen normally), cap at 0
        if reward_yocto < 0:
            reward_yocto = Decimal('0')

        reward_near = reward_yocto / YOCTO

        # Get epoch date and prices
        epoch_date = epoch_timestamp_to_date(epoch_ts)
        price_usd = get_near_price(epoch_date, 'usd')

        if price_usd:
            reward_usd = reward_near * price_usd
            usd_to_cad = get_exchange_rate(epoch_date, 'USD', 'CAD')
            price_cad = price_usd * usd_to_cad
            reward_cad = reward_usd * usd_to_cad
        else:
            price_cad = None
            reward_usd = None
            reward_cad = None

        # Insert the calculated reward
        try:
            cur.execute("""
                INSERT INTO staking_epoch_rewards
                    (wallet_id, validator_id, epoch_id, epoch_timestamp, epoch_date,
                     balance_before, balance_after, deposits, withdrawals,
                     reward_yocto, reward_near, near_price_usd, near_price_cad,
                     reward_usd, reward_cad, calculation_method)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'snapshot')
            """, (
                wallet_id, validator_id, epoch_id, epoch_ts, epoch_date,
                str(prev_balance), str(current_balance), str(deposits), str(withdrawals),
                str(reward_yocto), float(reward_near),
                float(price_usd) if price_usd else None,
                float(price_cad) if price_cad else None,
                float(reward_usd) if reward_usd else None,
                float(reward_cad) if reward_cad else None
            ))
            conn.commit()

            print(f"  {account_id} @ {validator_id}: {float(reward_near):.6f} NEAR "
                  f"(${float(reward_usd):.4f} USD)" if reward_usd else
                  f"  {account_id} @ {validator_id}: {float(reward_near):.6f} NEAR")
            rewards_calculated += 1

        except Exception as e:
            print(f"  Error saving reward: {e}")
            conn.rollback()

    conn.close()
    return rewards_calculated


def get_latest_snapshot_epoch():
    """Get the latest epoch ID from snapshots."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT MAX(epoch_id) FROM staking_balance_snapshots")
    row = cur.fetchone()
    conn.close()

    return row[0] if row else None


def backfill_all_epochs():
    """Calculate rewards for all epochs that have snapshots."""
    conn = get_db()
    cur = conn.cursor()

    # Get all epochs with snapshots, ordered
    cur.execute("""
        SELECT DISTINCT epoch_id FROM staking_balance_snapshots
        ORDER BY epoch_id
    """)

    epochs = [row[0] for row in cur.fetchall()]
    conn.close()

    if len(epochs) < 2:
        print("Need at least 2 epochs of snapshots to calculate rewards")
        return

    print(f"Found {len(epochs)} epochs: {epochs}")

    # Skip the first epoch (no previous to compare)
    total_rewards = 0
    for epoch_id in epochs[1:]:
        print(f"\nCalculating rewards for epoch {epoch_id}...")
        rewards = calculate_rewards_for_epoch(epoch_id)
        total_rewards += rewards

    print(f"\nBackfill complete! Calculated {total_rewards} rewards")


def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='Calculate epoch staking rewards')
    parser.add_argument('--backfill', action='store_true',
                        help='Backfill rewards for all available epochs')
    parser.add_argument('--epoch', type=int,
                        help='Calculate rewards for a specific epoch')
    args = parser.parse_args()

    if args.backfill:
        backfill_all_epochs()
    elif args.epoch:
        print(f"Calculating rewards for epoch {args.epoch}...")
        rewards = calculate_rewards_for_epoch(args.epoch)
        print(f"Done! Calculated {rewards} rewards")
    else:
        # Default: calculate for latest epoch
        latest_epoch = get_latest_snapshot_epoch()
        if latest_epoch:
            print(f"Calculating rewards for latest epoch {latest_epoch}...")
            rewards = calculate_rewards_for_epoch(latest_epoch)
            print(f"Done! Calculated {rewards} rewards")
        else:
            print("No snapshots found. Run epoch_staking_snapshot.py first.")


if __name__ == '__main__':
    main()
#!/usr/bin/env python3
"""
Historical Staking Rewards Backfill for NearTax v2

Fixed version that properly handles deposits and balance tracking.
"""

import os
from decimal import Decimal, getcontext
import time

getcontext().prec = 50

PG_CONN = os.environ.get('DATABASE_URL',
    'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax')
NEAR_RPC = 'https://rpc.mainnet.near.org'
CRYPTOCOMPARE_API = 'https://min-api.cryptocompare.com/data'
YOCTO = Decimal('1e24')

EPOCH_DURATION_NS = int(12 * 3600 * 1e9)  # 12 hours in nanoseconds


def get_db():  # noqa: F811 — standalone script section
    return psycopg2.connect(PG_CONN)


def nanoseconds_to_datetime(ns: int) -> datetime:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)


def get_near_price_cached(date_str: str, currency: str = 'usd') -> Decimal:
    """Get NEAR price for a specific date from CryptoCompare or cache."""
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
        print(f"  Error fetching price for {date_str}: {e}")

    conn.close()
    return None


def get_exchange_rate(date_str: str, from_currency: str = 'USD', to_currency: str = 'CAD') -> Decimal:  # noqa: F811
    conn = get_db()
    cur = conn.cursor()

    if from_currency.upper() == 'USD' and to_currency.upper() == 'CAD':
        cur.execute("SELECT rate FROM exchange_rate_history WHERE date = %s", (date_str,))
        row = cur.fetchone()
        if row:
            conn.close()
            return Decimal(str(row[0]))

    cur.execute("""
        SELECT rate FROM exchange_rates
        WHERE from_currency = %s AND to_currency = %s AND date = %s
    """, (from_currency.upper(), to_currency.upper(), date_str))

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


def get_staking_history(wallet_id: int, validator_id: str):
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


def get_current_staked_balance(validator_id: str, account_id: str) -> Decimal:
    args = json.dumps({'account_id': account_id})
    args_b64 = base64.b64encode(args.encode()).decode()

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
    return Decimal('0')


def calculate_epoch_rewards_backfill(wallet_id: int, account_id: str, validator_id: str):
    """
    Calculate and insert historical epoch rewards with proper deposit tracking.
    """
    print(f"\n=== Backfilling {account_id} @ {validator_id} ===")

    events = get_staking_history(wallet_id, validator_id)
    if not events:
        print("  No staking events found")
        return 0

    # Build deposit/withdrawal timeline
    deposit_events = []  # [(timestamp, amount_change)]
    total_deposits = Decimal('0')
    first_stake_ts = None

    for event in events:
        if event['event_type'] in ('stake', 'deposit_and_stake'):
            total_deposits += event['amount']
            deposit_events.append((event['timestamp'], event['amount']))
            if first_stake_ts is None:
                first_stake_ts = event['timestamp']
        elif event['event_type'] in ('unstake', 'withdraw', 'withdraw_all'):
            deposit_events.append((event['timestamp'], -event['amount']))

    if first_stake_ts is None:
        print("  No stake events found")
        return 0

    print(f"  First stake: {nanoseconds_to_datetime(first_stake_ts).strftime('%Y-%m-%d %H:%M')}")
    print(f"  Total deposited: {total_deposits / YOCTO:.2f} NEAR")

    # Get current balance and epoch info
    current_balance = get_current_staked_balance(validator_id, account_id)
    print(f"  Current balance: {current_balance / YOCTO:.2f} NEAR")

    current_epoch_info = get_current_epoch_info()
    current_epoch = current_epoch_info['epoch_height']
    int(datetime.now(timezone.utc).timestamp() * 1e9)

    # Calculate epochs
    first_stake_dt = nanoseconds_to_datetime(first_stake_ts)
    now = datetime.now(timezone.utc)
    time_delta = now - first_stake_dt
    num_epochs = int(time_delta.total_seconds() / (12 * 3600))
    first_epoch = current_epoch - num_epochs

    print(f"  Epochs: {first_epoch} to {current_epoch} ({num_epochs} epochs)")

    # Check existing data
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
        return 0

    num_backfill_epochs = backfill_to_epoch - first_epoch + 1
    print(f"  Will backfill {num_backfill_epochs} epochs ({first_epoch} to {backfill_to_epoch})")

    # Sort deposit events by timestamp
    deposit_events.sort(key=lambda x: x[0])

    # Calculate the balance at each epoch by tracking deposits and rewards
    # We need to work backwards from current balance to figure out per-epoch rate

    # First, calculate balance timeline from deposits only (no rewards yet)
    epoch_deposits = {}  # epoch_id -> total deposits in that epoch
    for ts, amount in deposit_events:
        # Find which epoch this deposit belongs to
        time_since_first = ts - first_stake_ts
        epoch_offset = int(time_since_first / EPOCH_DURATION_NS)
        epoch_id = first_epoch + epoch_offset

        if epoch_id not in epoch_deposits:
            epoch_deposits[epoch_id] = Decimal('0')
        epoch_deposits[epoch_id] += amount

    print(f"  Deposit events by epoch: {[(e, float(v/YOCTO)) for e, v in sorted(epoch_deposits.items())]}")

    # Calculate total rewards (current balance - net deposits)
    net_deposits = total_deposits  # Assuming no withdrawals based on events
    total_rewards = current_balance - net_deposits
    print(f"  Total rewards earned: {total_rewards / YOCTO:.4f} NEAR")

    if total_rewards <= 0:
        print("  No positive rewards to backfill")
        conn.close()
        return 0

    # Calculate implied per-epoch rate using compound interest
    # Balance grows from net_deposits to current_balance over num_epochs
    # current_balance = net_deposits * (1 + r)^n
    # r = (current_balance / net_deposits)^(1/n) - 1

    implied_rate = (current_balance / net_deposits) ** (Decimal('1') / Decimal(num_epochs)) - 1
    print(f"  Implied per-epoch rate: {float(implied_rate * 100):.6f}%")
    print(f"  Implied annual APY: {float(((1 + implied_rate) ** 730 - 1) * 100):.2f}%")

    # Now simulate forward: track balance with deposits and compound rewards
    balance = Decimal('0')
    rewards_inserted = 0
    batch_count = 0
    batch_size = 50

    for epoch_offset in range(num_backfill_epochs):
        epoch_id = first_epoch + epoch_offset

        # Add any deposits for this epoch
        if epoch_id in epoch_deposits:
            deposit_amount = epoch_deposits[epoch_id]
            balance += deposit_amount
            deposits_this_epoch = deposit_amount
        else:
            deposits_this_epoch = Decimal('0')

        # Calculate epoch timestamp
        epoch_ts = first_stake_ts + (epoch_offset * EPOCH_DURATION_NS)
        epoch_dt = nanoseconds_to_datetime(epoch_ts)
        epoch_date = epoch_dt.strftime('%Y-%m-%d')

        # Skip if no balance yet (before first deposit fully applied)
        if balance <= 0:
            continue

        # Calculate reward for this epoch
        balance_before = balance
        reward_yocto = balance * implied_rate
        balance_after = balance + reward_yocto
        balance = balance_after

        reward_near = reward_yocto / YOCTO

        # Get prices
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

        # Insert record
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
                time.sleep(0.1)

        except Exception as e:
            print(f"  Error inserting epoch {epoch_id}: {e}")
            conn.rollback()

    conn.commit()

    # Verify final balance
    print(f"  Final simulated balance: {balance / YOCTO:.4f} NEAR")
    print(f"  Actual current balance: {current_balance / YOCTO:.4f} NEAR")
    print(f"  Difference: {(current_balance - balance) / YOCTO:.4f} NEAR (accounts for most recent epoch)")

    conn.close()
    print(f"  Inserted {rewards_inserted} epoch reward records")
    return rewards_inserted


def get_wallet_info(wallet_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT account_id FROM wallets WHERE id = %s", (wallet_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Backfill historical staking rewards')
    parser.add_argument('--wallet-id', type=int, help='Specific wallet ID')
    parser.add_argument('--validator', type=str, help='Specific validator')
    parser.add_argument('--all', action='store_true', help='Backfill all wallets')
    args = parser.parse_args()

    if args.wallet_id and args.validator:
        account_id = get_wallet_info(args.wallet_id)
        if account_id:
            calculate_epoch_rewards_backfill(args.wallet_id, account_id, args.validator)
        else:
            print(f"Wallet {args.wallet_id} not found")
    elif args.all:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT DISTINCT se.wallet_id, w.account_id, se.validator_id
            FROM staking_events se
            JOIN wallets w ON se.wallet_id = w.id
            WHERE se.event_type IN ('stake', 'deposit_and_stake')
            ORDER BY se.wallet_id
        """)

        wallet_validators = cur.fetchall()
        conn.close()

        total_inserted = 0
        for wallet_id, account_id, validator_id in wallet_validators:
            count = calculate_epoch_rewards_backfill(wallet_id, account_id, validator_id)
            total_inserted += count

        print("\n=== COMPLETE ===")
        print(f"Total epoch rewards inserted: {total_inserted}")
    else:
        print("Backfilling Kevin's staking rewards (wallet 97, vitalpoint.pool.near)")
        account_id = get_wallet_info(97)
        if account_id:
            calculate_epoch_rewards_backfill(97, account_id, 'vitalpoint.pool.near')


if __name__ == '__main__':
    main()
