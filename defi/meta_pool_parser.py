#!/usr/bin/env python3
"""
Meta Pool (metapool.app) liquid staking parser.

Meta Pool provides liquid staking on NEAR - you stake NEAR and receive stNEAR.
Tax implications:
- Stake NEAR → receive stNEAR: Non-taxable exchange
- Unstake stNEAR → receive NEAR: May have gain if stNEAR appreciated
- stNEAR appreciation: Taxed when realized (on unstake or trade)
- META token rewards: Taxable income at FMV
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from indexers.price_service import get_hourly_price

# Meta Pool contracts
META_POOL_CONTRACTS = [
    "meta-pool.near",
    "meta-v2.pool.near",
]

# Tokens
STNEAR_CONTRACT = "meta-pool.near"  # stNEAR token
META_TOKEN = "meta-token.near"  # META governance token


def parse_meta_pool_transactions():
    """Parse all Meta Pool-related FT transactions."""
    conn = get_connection()

    # Check if defi_events table exists
    try:
        conn.execute("SELECT 1 FROM defi_events LIMIT 1")
    except Exception:
        from defi.burrow_parser import create_defi_events_table
        create_defi_events_table()

    # Find all FT transactions involving Meta Pool
    cur = conn.execute("""
        SELECT ft.id, ft.wallet_id, ft.token_contract, ft.token_symbol,
               ft.amount, ft.counterparty, ft.direction, ft.cause,
               ft.tx_hash, ft.block_timestamp, ft.token_decimals,
               w.account_id
        FROM ft_transactions ft
        JOIN wallets w ON ft.wallet_id = w.id
        WHERE ft.counterparty LIKE '%meta-pool%'
           OR ft.token_contract = 'meta-pool.near'
           OR ft.token_contract = 'meta-token.near'
           OR ft.token_symbol = 'STNEAR'
           OR ft.token_symbol = '$META'
        ORDER BY ft.block_timestamp
    """)

    transactions = cur.fetchall()
    print(f"Found {len(transactions)} Meta Pool-related FT transactions")

    events = []

    for row in transactions:
        (ft_id, wallet_id, token_contract, token_symbol, amount,
         counterparty, direction, cause, tx_hash, timestamp, decimals, account_id) = row

        # Parse amount
        try:
            decimals = decimals or 24  # NEAR uses 24 decimals
            amount_decimal = float(amount) / (10 ** decimals) if amount else 0
        except Exception:
            amount_decimal = 0

        event_type = None
        tax_category = None
        tax_notes = None
        needs_review = 0

        # stNEAR transactions
        if token_symbol == "STNEAR" or "stnear" in (token_contract or "").lower():
            if direction == "in":
                event_type = "liquid_stake"
                tax_category = "stake"
                tax_notes = "Received stNEAR - liquid staking position"
            else:
                event_type = "liquid_unstake"
                tax_category = "unstake"
                tax_notes = "Sent stNEAR - may have gain if stNEAR appreciated"
                needs_review = 1

        # META token (rewards/governance)
        elif token_symbol == "$META" or token_contract == META_TOKEN:
            if direction == "in":
                event_type = "meta_reward"
                tax_category = "income"
                tax_notes = "META token received - taxable as income at FMV"
            else:
                event_type = "meta_transfer"
                tax_category = "transfer"
                tax_notes = "META token sent"

        # Get price
        price_usd = None
        value_usd = None

        if token_symbol == "STNEAR" and timestamp:
            # stNEAR ~= NEAR price (slight premium usually)
            price_usd = get_hourly_price("NEAR", timestamp)
            if price_usd:
                value_usd = amount_decimal * price_usd * 1.05  # ~5% premium estimate

        if event_type:
            events.append({
                "wallet_id": wallet_id,
                "protocol": "meta_pool",
                "event_type": event_type,
                "token_contract": token_contract,
                "token_symbol": token_symbol,
                "amount": amount,
                "amount_decimal": amount_decimal,
                "counterparty": counterparty,
                "tx_hash": tx_hash,
                "block_timestamp": timestamp,
                "price_usd": price_usd,
                "value_usd": value_usd,
                "tax_category": tax_category,
                "tax_notes": tax_notes,
                "needs_review": needs_review,
            })

    # Insert events
    for e in events:
        conn.execute("""
            INSERT INTO defi_events
            (wallet_id, protocol, event_type, token_contract, token_symbol,
             amount, amount_decimal, counterparty, tx_hash, block_timestamp,
             price_usd, value_usd, tax_category, tax_notes, needs_review)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            e["wallet_id"], e["protocol"], e["event_type"], e["token_contract"],
            e["token_symbol"], e["amount"], e["amount_decimal"], e["counterparty"],
            e["tx_hash"], e["block_timestamp"], e["price_usd"], e["value_usd"],
            e["tax_category"], e["tax_notes"], e["needs_review"]
        ))

    conn.commit()
    conn.close()

    print(f"Created {len(events)} Meta Pool DeFi events")
    return events


def get_meta_pool_summary():
    """Get summary of Meta Pool activity."""
    conn = get_connection()

    cur = conn.execute("""
        SELECT
            event_type,
            token_symbol,
            SUM(amount_decimal) as total_amount,
            SUM(value_usd) as total_usd,
            COUNT(*) as count
        FROM defi_events
        WHERE protocol = 'meta_pool'
        GROUP BY event_type, token_symbol
        ORDER BY count DESC
    """)

    print("\n=== Meta Pool Activity Summary ===")
    print(f"{'Event':<20} {'Token':<10} {'Amount':>15} {'USD':>15} {'Count':>8}")
    print("-" * 70)

    for row in cur.fetchall():
        event, token, amount, usd, count = row
        amount = amount or 0
        usd = usd or 0
        print(f"{event:<20} {token or '?':<10} {amount:>15,.2f} {usd:>15,.2f} {count:>8}")

    conn.close()


if __name__ == "__main__":
    parse_meta_pool_transactions()
    get_meta_pool_summary()
