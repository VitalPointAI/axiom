#!/usr/bin/env python3
"""
Ref Finance (ref.finance) DeFi parser.

Ref Finance is the main DEX on NEAR. Tax implications:
- Swap: Capital gain/loss on disposal of one asset for another
- Add liquidity: Non-taxable (but track cost basis of LP tokens)
- Remove liquidity: May have capital gain/loss (impermanent loss)
- Farming rewards: Taxable income at FMV
- REF token rewards: Taxable income at FMV
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from indexers.price_service import get_hourly_price

# Ref Finance contracts
REF_CONTRACTS = [
    "v2.ref-finance.near",
    "ref-finance.near",
    "boostfarm.ref-finance.near",
    "ref-farming.near",
]

# REF token
REF_TOKEN = "token.ref-finance.near"


def parse_ref_transactions():
    """Parse all Ref Finance-related FT transactions."""
    conn = get_connection()
    
    # Check if defi_events table exists (created by burrow parser)
    try:
        conn.execute("SELECT 1 FROM defi_events LIMIT 1")
    except Exception as e:
        logger.warning("defi_events table not found, creating it: %s", e)
        from defi.burrow_parser import create_defi_events_table
        create_defi_events_table()
    
    # Find all FT transactions involving Ref Finance
    cur = conn.execute("""
        SELECT ft.id, ft.wallet_id, ft.token_contract, ft.token_symbol, 
               ft.amount, ft.counterparty, ft.direction, ft.cause,
               ft.tx_hash, ft.block_timestamp, ft.token_decimals,
               w.account_id
        FROM ft_transactions ft
        JOIN wallets w ON ft.wallet_id = w.id
        WHERE ft.counterparty LIKE '%ref-finance%'
           OR ft.counterparty LIKE '%ref-farming%'
           OR ft.token_contract = 'token.ref-finance.near'
        ORDER BY ft.block_timestamp
    """)
    
    transactions = cur.fetchall()
    print(f"Found {len(transactions)} Ref Finance-related FT transactions")
    
    # Group transactions by tx_hash to identify swaps (in + out in same tx)
    tx_groups = defaultdict(list)
    for row in transactions:
        tx_hash = row[8]
        tx_groups[tx_hash].append(row)
    
    events = []
    processed_txs = set()
    
    for tx_hash, txs in tx_groups.items():
        if tx_hash in processed_txs:
            continue
        
        # Analyze the transaction group
        ins = [t for t in txs if t[6] == "in"]
        outs = [t for t in txs if t[6] == "out"]
        
        for row in txs:
            (ft_id, wallet_id, token_contract, token_symbol, amount, 
             counterparty, direction, cause, tx_hash, timestamp, decimals, account_id) = row
            
            # Parse amount
            try:
                decimals = decimals or 18
                amount_decimal = float(amount) / (10 ** decimals) if amount else 0
            except (ValueError, TypeError, ZeroDivisionError) as e:
                logger.warning("Failed to parse amount for tx %s (contract %s): %s", tx_hash, token_contract, e)
                amount_decimal = 0
            
            # Determine event type
            event_type = None
            tax_category = None
            tax_notes = None
            needs_review = 0
            
            # REF token rewards from farming
            if token_contract == REF_TOKEN and direction == "in":
                if "farm" in (counterparty or "").lower() or "boost" in (counterparty or "").lower():
                    event_type = "farming_reward"
                    tax_category = "income"
                    tax_notes = "REF farming reward - taxable as income at FMV"
                else:
                    event_type = "ref_received"
                    tax_category = "income"
                    tax_notes = "REF token received - review if reward or trade"
                    needs_review = 1
            
            # Swap detection: has both in and out in same tx
            elif len(ins) > 0 and len(outs) > 0:
                if direction == "out":
                    event_type = "swap_out"
                    tax_category = "trade"
                    tax_notes = "Swap - disposed of asset (capital gain/loss)"
                else:
                    event_type = "swap_in"
                    tax_category = "trade"
                    tax_notes = "Swap - received asset"
            
            # Liquidity operations
            elif direction == "out" and "ref-finance" in (counterparty or ""):
                event_type = "add_liquidity"
                tax_category = "liquidity_in"
                tax_notes = "Added liquidity - track cost basis of LP position"
            
            elif direction == "in" and "ref-finance" in (counterparty or ""):
                if token_symbol and "LP" in token_symbol.upper():
                    event_type = "lp_token_received"
                    tax_category = "liquidity_in"
                    tax_notes = "Received LP token"
                else:
                    event_type = "remove_liquidity"
                    tax_category = "liquidity_out"
                    tax_notes = "Removed liquidity - may have impermanent loss"
                    needs_review = 1
            
            # Get price
            price_usd = None
            value_usd = None
            
            if token_symbol in ["USDC", "USDT", "USN", "DAI"]:
                price_usd = 1.0
                value_usd = amount_decimal
            elif token_symbol == "wNEAR" and timestamp:
                price_usd = get_hourly_price("NEAR", timestamp)
                if price_usd:
                    value_usd = amount_decimal * price_usd
            elif token_symbol == "REF" and timestamp:
                # REF price - would need separate lookup
                # For now, mark for review
                needs_review = 1
            
            if event_type:
                events.append({
                    "wallet_id": wallet_id,
                    "protocol": "ref_finance",
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
        
        processed_txs.add(tx_hash)
    
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
    
    print(f"Created {len(events)} Ref Finance DeFi events")
    return events


def get_ref_summary():
    """Get summary of Ref Finance activity."""
    conn = get_connection()
    
    cur = conn.execute("""
        SELECT 
            event_type,
            token_symbol,
            SUM(amount_decimal) as total_amount,
            SUM(value_usd) as total_usd,
            COUNT(*) as count
        FROM defi_events
        WHERE protocol = 'ref_finance'
        GROUP BY event_type, token_symbol
        ORDER BY count DESC
    """)
    
    print("\n=== Ref Finance Activity Summary ===")
    print(f"{'Event':<20} {'Token':<10} {'Amount':>15} {'USD':>15} {'Count':>8}")
    print("-" * 70)
    
    total_swaps = 0
    total_rewards = 0
    
    for row in cur.fetchall():
        event, token, amount, usd, count = row
        amount = amount or 0
        usd = usd or 0
        print(f"{event:<20} {token or '?':<10} {amount:>15,.2f} {usd:>15,.2f} {count:>8}")
        
        if "swap" in event:
            total_swaps += count
        if event == "farming_reward":
            total_rewards += usd
    
    print("-" * 70)
    print(f"Total Swaps: {total_swaps}")
    print(f"Total Farming Rewards (Taxable): ${total_rewards:,.2f}")
    
    conn.close()


def get_ref_tax_summary_by_year():
    """Get Ref Finance taxable events by year."""
    conn = get_connection()
    
    cur = conn.execute("""
        SELECT 
            strftime('%Y', datetime(block_timestamp/1000000000, 'unixepoch')) as year,
            tax_category,
            COUNT(*) as events,
            SUM(CASE WHEN value_usd IS NOT NULL THEN value_usd ELSE 0 END) as total_usd
        FROM defi_events
        WHERE protocol = 'ref_finance'
        AND block_timestamp IS NOT NULL
        GROUP BY year, tax_category
        ORDER BY year, tax_category
    """)
    
    print("\n=== Ref Finance Tax Events by Year ===")
    for row in cur.fetchall():
        year, category, events, usd = row
        print(f"  {year} - {category}: {events} events (${usd:,.2f} valued)")
    
    conn.close()


if __name__ == "__main__":
    parse_ref_transactions()
    get_ref_summary()
    get_ref_tax_summary_by_year()
