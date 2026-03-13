#!/usr/bin/env python3
"""
Burrow Finance Historical Transaction Parser

Parses FT transactions involving Burrow to track:
- Supply/Withdraw events
- Borrow/Repay events  
- BRRR reward income
- Liquidations

Tax implications:
- Supply/Withdraw: Non-taxable (moving collateral)
- Borrow/Repay: Non-taxable (loan mechanics)
- BRRR rewards: Taxable income at FMV
- Interest earned: Taxable income
- Liquidation: Capital loss
"""

import logging
import psycopg2
from datetime import datetime

logger = logging.getLogger(__name__)

PG_CONN = 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'

BURROW_CONTRACTS = [
    'contract.main.burrow.near',
    'burrow.near',
]

BRRR_CONTRACT = 'token.burrow.near'

# Token decimals (Burrow uses 18 internally for most)
TOKEN_DECIMALS = {
    'wrap.near': 24,
    'lst.rhealab.near': 24,  # rNEAR
    'meta-pool.near': 24,  # stNEAR
    'token.burrow.near': 18,  # BRRR
}

def get_decimals(token_contract):
    return TOKEN_DECIMALS.get(token_contract, 18)


def parse_burrow_history():
    """Parse all Burrow-related FT transactions into defi_events."""
    conn = psycopg2.connect(PG_CONN)
    cur = conn.cursor()
    
    # Get all FT transactions involving Burrow
    cur.execute("""
        SELECT 
            ft.id, ft.wallet_id, ft.token_contract, ft.token_symbol,
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
    
    # Clear existing burrow events from defi_events (we'll rebuild)
    cur.execute("DELETE FROM defi_events WHERE protocol = 'burrow' AND event_type NOT IN ('supply', 'collateral', 'borrow')")
    
    events = []
    processed_count = 0
    
    for row in transactions:
        (ft_id, wallet_id, token_contract, token_symbol, amount,
         counterparty, direction, cause, tx_hash, timestamp, 
         token_decimals, account_id) = row
        
        # Parse amount
        try:
            decimals = token_decimals or get_decimals(token_contract)
            amount_decimal = float(amount) / (10 ** decimals) if amount else 0
        except (ValueError, TypeError, ZeroDivisionError) as e:
            logger.warning("Failed to parse amount for tx %s (contract %s): %s", tx_hash, token_contract, e)
            amount_decimal = 0
        
        # Determine event type and tax category
        event_type = None
        tax_category = None
        tax_notes = None
        needs_review = 0
        
        counterparty_lower = (counterparty or '').lower()
        is_burrow = 'burrow' in counterparty_lower
        
        # BRRR token rewards
        if token_contract == BRRR_CONTRACT or token_symbol == 'BRRR':
            if direction == 'in':
                event_type = 'brrr_reward'
                tax_category = 'income'
                tax_notes = 'BRRR farming/staking reward - taxable as income at FMV'
            else:
                event_type = 'brrr_transfer'
                tax_category = 'transfer'
                tax_notes = 'BRRR transferred out'
        
        # Supply (sending tokens TO Burrow)
        elif is_burrow and direction == 'out':
            event_type = 'supply'
            tax_category = 'collateral_in'
            tax_notes = 'Supplied to Burrow lending - non-taxable deposit'
        
        # Withdraw (receiving tokens FROM Burrow)
        elif is_burrow and direction == 'in':
            # Check if it might be a liquidation
            cause_lower = (cause or '').lower()
            if 'liquidat' in cause_lower:
                event_type = 'liquidation'
                tax_category = 'capital_loss'
                tax_notes = 'Liquidation event - may be capital loss, needs review'
                needs_review = 1
            elif 'borrow' in cause_lower:
                event_type = 'borrow'
                tax_category = 'loan_received'
                tax_notes = 'Borrowed from Burrow - non-taxable loan'
            elif 'repay' in cause_lower:
                # Repayment refund? Unusual
                event_type = 'repay_refund'
                tax_category = 'loan_repay'
                tax_notes = 'Repayment refund from Burrow'
                needs_review = 1
            else:
                event_type = 'withdraw'
                tax_category = 'collateral_out'
                tax_notes = 'Withdrawn from Burrow - non-taxable'
        
        if event_type:
            events.append({
                'wallet_id': wallet_id,
                'protocol': 'burrow',
                'event_type': event_type,
                'token_contract': token_contract,
                'token_symbol': token_symbol,
                'amount': str(amount),
                'amount_decimal': amount_decimal,
                'counterparty': counterparty,
                'tx_hash': tx_hash,
                'block_timestamp': timestamp,
                'price_usd': None,  # Will be filled by price service
                'value_usd': None,
                'tax_category': tax_category,
                'tax_notes': tax_notes,
                'needs_review': needs_review,
            })
            processed_count += 1
    
    # Insert events
    for e in events:
        cur.execute("""
            INSERT INTO defi_events 
            (wallet_id, protocol, event_type, token_contract, token_symbol,
             amount, amount_decimal, counterparty, tx_hash, block_timestamp,
             price_usd, value_usd, tax_category, tax_notes, needs_review)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            e['wallet_id'], e['protocol'], e['event_type'], e['token_contract'],
            e['token_symbol'], e['amount'], e['amount_decimal'], e['counterparty'],
            e['tx_hash'], e['block_timestamp'], e['price_usd'], e['value_usd'],
            e['tax_category'], e['tax_notes'], e['needs_review']
        ))
    
    conn.commit()
    
    # Summary
    cur.execute("""
        SELECT event_type, tax_category, COUNT(*), SUM(amount_decimal)
        FROM defi_events 
        WHERE protocol = 'burrow'
        GROUP BY event_type, tax_category
        ORDER BY count DESC
    """)
    
    print("\n=== Burrow Events Summary ===")
    print(f"{'Event':<20} {'Tax Category':<20} {'Count':>8} {'Total Amount':>15}")
    print("-" * 70)
    for row in cur.fetchall():
        event, category, count, total = row
        total = total or 0
        print(f"{event:<20} {category:<20} {count:>8} {total:>15,.4f}")
    
    cur.close()
    conn.close()
    
    print(f"\nCreated {len(events)} Burrow DeFi events")
    return events


def auto_categorize_flagged():
    """Auto-categorize the 974 flagged transactions that need review."""
    conn = psycopg2.connect(PG_CONN)
    cur = conn.cursor()
    
    # Get counts before
    cur.execute("SELECT COUNT(*) FROM defi_events WHERE needs_review = 1")
    before = cur.fetchone()[0]
    print(f"\nTransactions needing review before: {before}")
    
    # Meta Pool unstakes - these are taxable disposals
    # Selling stNEAR for NEAR is a taxable event
    cur.execute("""
        UPDATE defi_events 
        SET needs_review = 0,
            tax_category = 'trade',
            tax_notes = 'Unstaking stNEAR - taxable disposal, gain/loss based on stNEAR cost basis'
        WHERE protocol = 'meta_pool' 
        AND event_type = 'liquid_unstake'
        AND needs_review = 1
    """)
    mp_unstakes = cur.rowcount
    print(f"  Meta Pool unstakes categorized as trades: {mp_unstakes}")
    
    # Ref Finance LP additions - non-taxable (adding liquidity)
    cur.execute("""
        UPDATE defi_events 
        SET needs_review = 0,
            tax_category = 'liquidity_add',
            tax_notes = 'LP deposit - track cost basis of tokens added'
        WHERE protocol = 'ref_finance' 
        AND event_type IN ('lp_add', 'liquidity_in')
        AND needs_review = 1
    """)
    lp_adds = cur.rowcount
    print(f"  Ref LP additions categorized: {lp_adds}")
    
    # Ref Finance LP removals - may have gains if IL occurred
    cur.execute("""
        UPDATE defi_events 
        SET needs_review = 0,
            tax_category = 'liquidity_remove',
            tax_notes = 'LP withdrawal - compare to original deposit for IL gains/losses'
        WHERE protocol = 'ref_finance' 
        AND event_type IN ('lp_remove', 'liquidity_out')
        AND needs_review = 1
    """)
    lp_removes = cur.rowcount
    print(f"  Ref LP removals categorized: {lp_removes}")
    
    # Ref swaps - taxable trades
    cur.execute("""
        UPDATE defi_events 
        SET needs_review = 0,
            tax_category = 'trade',
            tax_notes = 'DEX swap - taxable disposal, calculate gain/loss'
        WHERE protocol = 'ref_finance' 
        AND event_type IN ('swap', 'swap_out', 'swap_in', 'trade')
        AND needs_review = 1
    """)
    swaps = cur.rowcount
    print(f"  Ref swaps categorized as trades: {swaps}")
    
    conn.commit()
    
    # Get counts after
    cur.execute("SELECT COUNT(*) FROM defi_events WHERE needs_review = 1")
    after = cur.fetchone()[0]
    print(f"\nTransactions still needing review: {after}")
    print(f"Auto-categorized: {before - after}")
    
    # Show remaining by type
    if after > 0:
        cur.execute("""
            SELECT protocol, event_type, COUNT(*) 
            FROM defi_events 
            WHERE needs_review = 1 
            GROUP BY protocol, event_type 
            ORDER BY count DESC
        """)
        print("\nRemaining uncategorized:")
        for row in cur.fetchall():
            print(f"  {row[0]}: {row[1]} ({row[2]})")
    
    cur.close()
    conn.close()


if __name__ == '__main__':
    print("=== Parsing Burrow History ===")
    parse_burrow_history()
    
    print("\n=== Auto-categorizing Flagged Transactions ===")
    auto_categorize_flagged()
