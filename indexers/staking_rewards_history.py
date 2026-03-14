#!/usr/bin/env python3
"""
Historical staking rewards tracker.

NEAR staking rewards accrue continuously but are only "received" when:
1. You unstake (rewards included in unstaked amount)
2. You restake (compound rewards)
3. Validator distributes rewards (varies by validator)

For tax purposes, we need to estimate when rewards were received.
This script analyzes balance changes over time to identify reward events.
"""

import time
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from db.init import get_connection
from indexers.price_service import get_hourly_price

NEARBLOCKS_API_KEY = config.NEARBLOCKS_API_KEY
NEARBLOCKS_BASE = "https://api.nearblocks.io/v1"


def get_headers():
    headers = {}
    if NEARBLOCKS_API_KEY:
        headers["Authorization"] = f"Bearer {NEARBLOCKS_API_KEY}"
    return headers


def create_rewards_table():
    """Create table for tracking individual reward events."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS staking_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            validator TEXT NOT NULL,
            reward_amount TEXT NOT NULL,
            reward_near REAL NOT NULL,
            block_timestamp INTEGER,
            price_usd REAL,
            value_usd REAL,
            reward_type TEXT DEFAULT 'estimated',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_staking_rewards_wallet ON staking_rewards(wallet_id)")
    conn.commit()
    conn.close()
    print("Staking rewards table created/verified")


def estimate_rewards_from_unstake_events(wallet_id: int, account_id: str, validator: str):
    """
    Estimate rewards based on unstake events.

    When you unstake, you get principal + accrued rewards.
    If unstake amount > deposit amount, the difference is rewards.
    """
    conn = get_connection()

    # Get all stake events in chronological order
    cur = conn.execute("""
        SELECT event_type, amount, block_timestamp, tx_hash
        FROM staking_events
        WHERE wallet_id = ? AND validator = ?
        ORDER BY block_timestamp
    """, (wallet_id, validator))

    events = cur.fetchall()

    if not events:
        conn.close()
        return []

    rewards = []
    running_principal = 0  # Track what was deposited

    for event_type, amount_str, timestamp, tx_hash in events:
        amount = int(amount_str) if amount_str else 0

        if event_type in ('deposit_and_stake', 'stake', 'stake_all'):
            running_principal += amount

        elif event_type in ('unstake', 'withdraw'):
            if amount > running_principal and running_principal > 0:
                # Unstaked more than deposited = rewards included
                reward_amount = amount - running_principal
                reward_near = reward_amount / 1e24

                # Get price at time of unstake
                price = get_hourly_price("NEAR", timestamp) if timestamp else None
                value_usd = reward_near * price if price else None

                rewards.append({
                    "wallet_id": wallet_id,
                    "validator": validator,
                    "reward_amount": str(reward_amount),
                    "reward_near": reward_near,
                    "block_timestamp": timestamp,
                    "price_usd": price,
                    "value_usd": value_usd,
                    "reward_type": "unstake_realized",
                    "notes": f"Rewards realized on unstake (tx: {tx_hash[:16]}...)" if tx_hash else "Rewards realized on unstake",
                })

                running_principal = 0  # Reset after full unstake
            else:
                running_principal = max(0, running_principal - amount)

        elif event_type in ('unstake_all', 'withdraw_all'):
            # Full unstake - any excess over principal is rewards
            # We'd need to query the actual unstaked amount from the blockchain
            # For now, mark as needing review
            running_principal = 0

    conn.close()
    return rewards


def estimate_annual_rewards(wallet_id: int, account_id: str, validator: str,
                           start_year: int = 2020, end_year: int = 2025):
    """
    Estimate rewards per year based on typical NEAR staking APY.

    This is a rough estimate for wallets that haven't unstaked yet.
    NEAR staking APY has ranged from ~8-12% historically.
    """
    conn = get_connection()

    # Get first stake date and current balance
    cur = conn.execute("""
        SELECT MIN(block_timestamp), MAX(block_timestamp)
        FROM staking_events
        WHERE wallet_id = ? AND validator = ?
    """, (wallet_id, validator))

    first_ts, last_ts = cur.fetchone()

    if not first_ts:
        conn.close()
        return []

    # Get total deposited
    cur = conn.execute("""
        SELECT SUM(CAST(amount AS REAL))
        FROM staking_events
        WHERE wallet_id = ? AND validator = ?
        AND event_type IN ('deposit_and_stake', 'stake', 'stake_all')
    """, (wallet_id, validator))
    total_deposited = (cur.fetchone()[0] or 0) / 1e24

    conn.close()

    if total_deposited == 0:
        return []

    # Estimate ~10% APY (conservative middle estimate)
    ESTIMATED_APY = 0.10

    rewards = []

    # Convert timestamps
    first_date = datetime.fromtimestamp(first_ts / 1_000_000_000) if first_ts > 1e12 else datetime.fromtimestamp(first_ts)

    for year in range(start_year, end_year + 1):
        year_start = datetime(year, 1, 1)
        year_end = datetime(year, 12, 31)

        if first_date > year_end:
            continue  # Haven't started staking yet

        # Calculate days staked in this year
        stake_start = max(first_date, year_start)
        stake_end = year_end  # Assume still staked

        days_staked = (stake_end - stake_start).days
        if days_staked <= 0:
            continue

        # Estimate rewards for this period
        yearly_reward_rate = ESTIMATED_APY * (days_staked / 365)
        estimated_reward = total_deposited * yearly_reward_rate

        # Get average price for the year (use mid-year)
        mid_year_ts = int(datetime(year, 7, 1).timestamp()) * 1_000_000_000
        price = get_hourly_price("NEAR", mid_year_ts)

        rewards.append({
            "wallet_id": None,  # Will be set later
            "validator": validator,
            "reward_amount": str(int(estimated_reward * 1e24)),
            "reward_near": estimated_reward,
            "block_timestamp": int(datetime(year, 12, 31).timestamp()) * 1_000_000_000,
            "price_usd": price,
            "value_usd": estimated_reward * price if price else None,
            "reward_type": "annual_estimate",
            "notes": f"Estimated rewards for {year} (~{ESTIMATED_APY*100:.0f}% APY, {days_staked} days)",
        })

    return rewards


def process_all_staking_rewards():
    """Process rewards for all staking positions."""
    create_rewards_table()

    conn = get_connection()

    # Get all staking positions
    cur = conn.execute("""
        SELECT DISTINCT se.wallet_id, w.account_id, se.validator
        FROM staking_events se
        JOIN wallets w ON se.wallet_id = w.id
    """)

    positions = cur.fetchall()

    print(f"Processing rewards for {len(positions)} staking positions...")

    total_rewards_near = 0
    total_rewards_usd = 0

    for wallet_id, account_id, validator in positions:
        print(f"\n{account_id} -> {validator}")

        # Try to find realized rewards from unstake events
        realized = estimate_rewards_from_unstake_events(wallet_id, account_id, validator)

        for r in realized:
            r["wallet_id"] = wallet_id
            total_rewards_near += r["reward_near"]
            if r["value_usd"]:
                total_rewards_usd += r["value_usd"]

            # Insert into database
            conn.execute("""
                INSERT INTO staking_rewards
                (wallet_id, validator, reward_amount, reward_near, block_timestamp,
                 price_usd, value_usd, reward_type, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["wallet_id"], r["validator"], r["reward_amount"], r["reward_near"],
                r["block_timestamp"], r["price_usd"], r["value_usd"],
                r["reward_type"], r["notes"]
            ))

            print(f"  Realized: {r['reward_near']:.2f} NEAR @ ${r['price_usd']:.2f}" if r['price_usd'] else f"  Realized: {r['reward_near']:.2f} NEAR")

        # If no realized rewards, estimate annual
        if not realized:
            estimates = estimate_annual_rewards(wallet_id, account_id, validator)
            for r in estimates:
                r["wallet_id"] = wallet_id
                if r["reward_near"] > 0:
                    total_rewards_near += r["reward_near"]
                    if r["value_usd"]:
                        total_rewards_usd += r["value_usd"]

                    conn.execute("""
                        INSERT INTO staking_rewards
                        (wallet_id, validator, reward_amount, reward_near, block_timestamp,
                         price_usd, value_usd, reward_type, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        r["wallet_id"], r["validator"], r["reward_amount"], r["reward_near"],
                        r["block_timestamp"], r["price_usd"], r["value_usd"],
                        r["reward_type"], r["notes"]
                    ))

                    print(f"  {r['notes']}: {r['reward_near']:.2f} NEAR")

        conn.commit()
        time.sleep(0.5)  # Rate limit for price lookups

    conn.close()

    print(f"\n{'='*60}")
    print(f"TOTAL REWARDS: {total_rewards_near:,.2f} NEAR")
    print(f"TOTAL VALUE: ${total_rewards_usd:,.2f} USD")
    print(f"{'='*60}")


def get_rewards_by_year():
    """Get staking rewards grouped by tax year."""
    conn = get_connection()

    cur = conn.execute("""
        SELECT
            strftime('%Y', datetime(block_timestamp/1000000000, 'unixepoch')) as year,
            SUM(reward_near) as total_near,
            SUM(value_usd) as total_usd,
            COUNT(*) as events
        FROM staking_rewards
        WHERE block_timestamp IS NOT NULL
        GROUP BY year
        ORDER BY year
    """)

    print("\n=== Staking Rewards by Tax Year ===")
    for row in cur.fetchall():
        year, near, usd, events = row
        print(f"  {year}: {near:,.2f} NEAR (${usd:,.2f} USD) - {events} events")

    conn.close()


if __name__ == "__main__":
    process_all_staking_rewards()
    get_rewards_by_year()
