#!/usr/bin/env python3
"""
Staking indexer for NEAR Protocol.
Tracks staking deposits, withdrawals, and rewards across all validators.
"""

import time
import requests
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from db.init import get_connection

# Load API key
NEARBLOCKS_API_KEY = config.NEARBLOCKS_API_KEY
NEARBLOCKS_BASE = "https://api.nearblocks.io/v1"


def get_headers():
    """Get API headers with auth."""
    headers = {}
    if NEARBLOCKS_API_KEY:
        headers["Authorization"] = f"Bearer {NEARBLOCKS_API_KEY}"
    return headers


def create_staking_tables():
    """Create staking-specific tables."""
    conn = get_connection()

    # Staking positions - current state with each validator
    conn.execute("""
        CREATE TABLE IF NOT EXISTS staking_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            validator TEXT NOT NULL,
            staked_amount TEXT DEFAULT '0',
            unstaked_amount TEXT DEFAULT '0',
            pending_withdrawal TEXT DEFAULT '0',
            total_rewards TEXT DEFAULT '0',
            first_stake_at INTEGER,
            last_activity_at INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(wallet_id, validator),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id)
        )
    """)

    # Staking events - individual stake/unstake/reward events
    conn.execute("""
        CREATE TABLE IF NOT EXISTS staking_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            validator TEXT NOT NULL,
            event_type TEXT NOT NULL,
            amount TEXT NOT NULL,
            tx_hash TEXT,
            block_height INTEGER,
            block_timestamp INTEGER,
            price_usd REAL,
            value_usd REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id)
        )
    """)

    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_staking_events_wallet ON staking_events(wallet_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_staking_events_validator ON staking_events(validator)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_staking_events_type ON staking_events(event_type)")

    conn.commit()
    conn.close()
    print("Staking tables created/verified")


def fetch_stake_txns(account_id: str, page: int = 1, per_page: int = 25) -> dict:
    """Fetch staking transactions for an account."""
    url = f"{NEARBLOCKS_BASE}/account/{account_id}/stake-txns"
    params = {"page": page, "per_page": per_page}

    resp = requests.get(url, headers=get_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_all_stake_txns(account_id: str) -> list:
    """Fetch all staking transactions for an account."""
    all_txns = []
    page = 1
    per_page = 100

    while True:
        data = fetch_stake_txns(account_id, page, per_page)
        txns = data.get("txns", [])

        if not txns:
            break

        all_txns.extend(txns)

        if len(txns) < per_page:
            break

        page += 1
        time.sleep(1.0)  # Rate limit - be conservative

    return all_txns


def parse_staking_event(tx: dict, account_id: str) -> dict | None:
    """Parse a staking transaction into an event."""
    actions = tx.get("actions", [])
    if not actions:
        return None

    action = actions[0]
    method = action.get("method", "")
    args = action.get("args", {})
    # Deposit is in actions_agg, not action
    deposit = str(int(tx.get("actions_agg", {}).get("deposit", 0)))

    receiver = tx.get("receiver_account_id", "")
    predecessor = tx.get("predecessor_account_id", "")

    # Determine validator
    validator = receiver if "pool" in receiver or "staking" in receiver else predecessor

    # Determine event type and amount
    event_type = None
    amount = "0"

    if method == "deposit_and_stake":
        event_type = "stake"
        amount = deposit
    elif method == "stake":
        event_type = "stake"
        amount = args.get("amount", deposit)
    elif method == "stake_all":
        event_type = "stake"
        amount = deposit
    elif method == "unstake":
        event_type = "unstake"
        amount = args.get("amount", "0")
    elif method == "unstake_all":
        event_type = "unstake_all"
        amount = "0"  # Full unstake, amount determined by position
    elif method == "withdraw":
        event_type = "withdraw"
        amount = args.get("amount", "0")
    elif method == "withdraw_all":
        event_type = "withdraw_all"
        amount = "0"
    elif method == "ping":
        # Ping distributes rewards - check if we received anything
        return None  # Skip pings for now
    else:
        # Unknown staking method
        return None

    return {
        "event_type": event_type,
        "validator": validator,
        "amount": amount,
        "tx_hash": tx.get("transaction_hash"),
        "block_height": tx.get("block", {}).get("block_height"),
        "block_timestamp": tx.get("block_timestamp"),
    }


def index_wallet_staking(wallet_id: int, account_id: str) -> int:
    """Index all staking activity for a wallet."""
    print(f"  Indexing staking for {account_id}...")

    # Fetch all staking transactions
    txns = fetch_all_stake_txns(account_id)
    print(f"    Found {len(txns)} staking transactions")

    if not txns:
        return 0

    conn = get_connection()
    events_added = 0
    validators = set()

    for tx in txns:
        event = parse_staking_event(tx, account_id)
        if not event:
            continue

        validators.add(event["validator"])

        # Check if event already exists
        existing = conn.execute(
            "SELECT id FROM staking_events WHERE tx_hash = ? AND wallet_id = ?",
            (event["tx_hash"], wallet_id)
        ).fetchone()

        if existing:
            continue

        # Insert event
        conn.execute("""
            INSERT INTO staking_events
            (wallet_id, validator, event_type, amount, tx_hash, block_height, block_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            wallet_id,
            event["validator"],
            event["event_type"],
            event["amount"],
            event["tx_hash"],
            event["block_height"],
            event["block_timestamp"],
        ))
        events_added += 1

    # Update/create staking positions
    for validator in validators:
        # Calculate totals from events
        cur = conn.execute("""
            SELECT event_type, SUM(CAST(amount AS INTEGER))
            FROM staking_events
            WHERE wallet_id = ? AND validator = ?
            GROUP BY event_type
        """, (wallet_id, validator))

        totals = dict(cur.fetchall())
        staked = totals.get("stake", 0) or 0
        unstaked = totals.get("unstake", 0) or 0

        # Get first/last timestamps
        cur = conn.execute("""
            SELECT MIN(block_timestamp), MAX(block_timestamp)
            FROM staking_events
            WHERE wallet_id = ? AND validator = ?
        """, (wallet_id, validator))
        first_ts, last_ts = cur.fetchone()

        # Upsert position
        conn.execute("""
            INSERT INTO staking_positions
            (wallet_id, validator, staked_amount, unstaked_amount, first_stake_at, last_activity_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(wallet_id, validator) DO UPDATE SET
                staked_amount = excluded.staked_amount,
                unstaked_amount = excluded.unstaked_amount,
                last_activity_at = excluded.last_activity_at,
                updated_at = CURRENT_TIMESTAMP
        """, (wallet_id, validator, str(staked), str(unstaked), first_ts, last_ts))

    conn.commit()
    conn.close()

    print(f"    Added {events_added} events, {len(validators)} validators")
    return events_added


def index_all_staking():
    """Index staking for all wallets."""
    create_staking_tables()

    conn = get_connection()
    wallets = conn.execute(
        "SELECT id, account_id FROM wallets WHERE chain = 'NEAR'"
    ).fetchall()
    conn.close()

    print(f"Indexing staking for {len(wallets)} wallets...")

    total_events = 0
    for wallet_id, account_id in wallets:
        try:
            events = index_wallet_staking(wallet_id, account_id)
            total_events += events
            time.sleep(1.0)  # Rate limit between wallets - paid API allows 190/min
        except Exception as e:
            print(f"  Error indexing {account_id}: {e}")

    print(f"\nDone! Total staking events indexed: {total_events}")
    return total_events


def get_staking_summary():
    """Get summary of all staking positions."""
    conn = get_connection()

    # Get all positions with wallet info
    cur = conn.execute("""
        SELECT
            w.account_id,
            sp.validator,
            sp.staked_amount,
            sp.unstaked_amount,
            sp.total_rewards,
            sp.first_stake_at,
            sp.last_activity_at
        FROM staking_positions sp
        JOIN wallets w ON sp.wallet_id = w.id
        ORDER BY CAST(sp.staked_amount AS INTEGER) DESC
    """)

    positions = cur.fetchall()
    conn.close()

    return positions


def get_staking_events_for_tax(wallet_id: int = None):
    """Get staking events formatted for tax reporting."""
    conn = get_connection()

    query = """
        SELECT
            se.event_type,
            se.validator,
            se.amount,
            se.block_timestamp,
            se.tx_hash,
            se.price_usd,
            se.value_usd,
            w.account_id
        FROM staking_events se
        JOIN wallets w ON se.wallet_id = w.id
    """

    if wallet_id:
        query += f" WHERE se.wallet_id = {wallet_id}"

    query += " ORDER BY se.block_timestamp"

    events = conn.execute(query).fetchall()
    conn.close()

    return events


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--summary":
        positions = get_staking_summary()
        print("\n=== Staking Positions ===")
        for pos in positions:
            account, validator, staked, unstaked, rewards, first, last = pos
            staked_near = int(staked) / 1e24 if staked else 0
            unstaked_near = int(unstaked) / 1e24 if unstaked else 0
            print(f"  {account} -> {validator}")
            print(f"    Staked: {staked_near:.2f} NEAR, Unstaked: {unstaked_near:.2f} NEAR")
    else:
        index_all_staking()
