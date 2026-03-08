#!/usr/bin/env python3
"""
Burrow Finance (burrow.finance) DeFi parser.

Burrow is a lending/borrowing protocol on NEAR. Tax implications:
- Supply: Non-taxable (deposit collateral)
- Withdraw: Non-taxable (unless liquidation)
- Borrow: Non-taxable (loan received)
- Repay: Non-taxable (loan repayment)
- Interest earned: Taxable income
- Interest paid: May be deductible
- Liquidation: Capital loss
- BRRR rewards: Taxable income at FMV
"""

import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from indexers.price_service import get_hourly_price

# Burrow contract addresses
BURROW_CONTRACTS = [
    "contract.main.burrow.near",
    "burrow.near",
]

# BRRR token (Burrow rewards)
BRRR_CONTRACT = "token.burrow.near"


def create_defi_events_table():
    """Create table for DeFi events with tax categorization."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS defi_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            protocol TEXT NOT NULL,
            event_type TEXT NOT NULL,
            token_contract TEXT,
            token_symbol TEXT,
            amount TEXT,
            amount_decimal REAL,
            counterparty TEXT,
            tx_hash TEXT,
            block_timestamp INTEGER,
            price_usd REAL,
            value_usd REAL,
            tax_category TEXT,
            tax_notes TEXT,
            needs_review INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_defi_events_wallet ON defi_events(wallet_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_defi_events_protocol ON defi_events(protocol)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_defi_events_type ON defi_events(event_type)")
    conn.commit()
    conn.close()


def parse_burrow_transactions():
    """Parse all Burrow-related FT transactions."""
    create_defi_events_table()
    
    conn = get_connection()
    
    # Find all FT transactions involving Burrow
    cur = conn.execute("""
        SELECT ft.id, ft.wallet_id, ft.token_contract, ft.token_symbol, 
               ft.amount, ft.counterparty, ft.direction, ft.cause,
               ft.tx_hash, ft.block_timestamp, ft.token_decimals,
               w.account_id
        FROM ft_transactions ft
        JOIN wallets w ON ft.wallet_id = w.id
        WHERE ft.counterparty LIKE '%burrow%'
           OR ft.token_contract = 'token.burrow.near'
        ORDER BY ft.block_timestamp
    """)
    
    transactions = cur.fetchall()
    print(f"Found {len(transactions)} Burrow-related FT transactions")
    
    events = []
    
    for row in transactions:
        (ft_id, wallet_id, token_contract, token_symbol, amount, 
         counterparty, direction, cause, tx_hash, timestamp, decimals, account_id) = row
        
        # Parse amount
        try:
            decimals = decimals or 18
            amount_decimal = float(amount) / (10 ** decimals) if amount else 0
        except:
            amount_decimal = 0
        
        # Determine event type and tax category
        event_type = None
        tax_category = None
        tax_notes = None
        needs_review = 0
        
        # BRRR rewards
        if token_contract == BRRR_CONTRACT:
            if direction == "in":
                event_type = "brrr_reward"
                tax_category = "income"
                tax_notes = "BRRR farming reward - taxable as income at FMV"
            else:
                event_type = "brrr_transfer"
                tax_category = "transfer"
                tax_notes = "BRRR transfer out"
        
        # Supply/Withdraw
        elif "burrow" in (counterparty or "").lower():
            if direction == "out":
                event_type = "supply"
                tax_category = "collateral_in"
                tax_notes = "Supplied to Burrow - non-taxable collateral deposit"
            else:
                event_type = "withdraw"
                tax_category = "collateral_out"
                tax_notes = "Withdrawn from Burrow - non-taxable"
                
                # Check if this might be liquidation (need more context)
                if cause and "liquidat" in cause.lower():
                    event_type = "liquidation"
                    tax_category = "capital_loss"
                    tax_notes = "Liquidation - may be capital loss"
                    needs_review = 1
        
        # Get price at time of transaction
        price_usd = None
        value_usd = None
        
        if token_symbol in ["USDC", "USDT", "USN", "DAI"]:
            price_usd = 1.0
            value_usd = amount_decimal
        elif token_symbol == "wNEAR" and timestamp:
            price_usd = get_hourly_price("NEAR", timestamp)
            if price_usd:
                value_usd = amount_decimal * price_usd
        
        if event_type:
            events.append({
                "wallet_id": wallet_id,
                "protocol": "burrow",
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
    
    print(f"Created {len(events)} Burrow DeFi events")
    return events


def get_burrow_summary():
    """Get summary of Burrow activity."""
    conn = get_connection()
    
    cur = conn.execute("""
        SELECT 
            event_type,
            token_symbol,
            SUM(amount_decimal) as total_amount,
            SUM(value_usd) as total_usd,
            COUNT(*) as count
        FROM defi_events
        WHERE protocol = 'burrow'
        GROUP BY event_type, token_symbol
        ORDER BY total_usd DESC NULLS LAST
    """)
    
    print("\n=== Burrow Activity Summary ===")
    print(f"{'Event':<20} {'Token':<10} {'Amount':>15} {'USD':>15} {'Count':>8}")
    print("-" * 70)
    
    total_income = 0
    
    for row in cur.fetchall():
        event, token, amount, usd, count = row
        amount = amount or 0
        usd = usd or 0
        print(f"{event:<20} {token or '?':<10} {amount:>15,.2f} {usd:>15,.2f} {count:>8}")
        
        if event == "brrr_reward":
            total_income += usd
    
    print("-" * 70)
    print(f"Total BRRR Rewards (Taxable Income): ${total_income:,.2f}")
    
    conn.close()


def get_burrow_tax_summary_by_year():
    """Get Burrow taxable events by year."""
    conn = get_connection()
    
    cur = conn.execute("""
        SELECT 
            strftime('%Y', datetime(block_timestamp/1000000000, 'unixepoch')) as year,
            tax_category,
            SUM(value_usd) as total_usd,
            COUNT(*) as events
        FROM defi_events
        WHERE protocol = 'burrow'
        AND tax_category IN ('income', 'capital_loss')
        AND block_timestamp IS NOT NULL
        GROUP BY year, tax_category
        ORDER BY year, tax_category
    """)
    
    print("\n=== Burrow Tax Events by Year ===")
    for row in cur.fetchall():
        year, category, usd, events = row
        usd = usd or 0
        print(f"  {year} - {category}: ${usd:,.2f} ({events} events)")
    
    conn.close()


if __name__ == "__main__":
    parse_burrow_transactions()
    get_burrow_summary()
    get_burrow_tax_summary_by_year()
