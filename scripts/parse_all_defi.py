#!/usr/bin/env python3
"""Run all DeFi parsers and generate summary."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from defi.burrow_parser import parse_burrow_transactions, get_burrow_summary, get_burrow_tax_summary_by_year
from defi.ref_finance_parser import parse_ref_transactions, get_ref_summary, get_ref_tax_summary_by_year
from defi.meta_pool_parser import parse_meta_pool_transactions, get_meta_pool_summary
from db.init import get_connection


def clear_defi_events():
    """Clear existing DeFi events for re-processing."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM defi_events")
        conn.commit()
        print("Cleared existing DeFi events")
    except:
        pass
    conn.close()


def get_full_defi_summary():
    """Get combined DeFi summary across all protocols."""
    conn = get_connection()
    
    print("\n" + "=" * 70)
    print("FULL DEFI TAX SUMMARY")
    print("=" * 70)
    
    # Events by protocol
    cur = conn.execute("""
        SELECT protocol, COUNT(*) as events, 
               SUM(CASE WHEN value_usd IS NOT NULL THEN value_usd ELSE 0 END) as total_usd
        FROM defi_events
        GROUP BY protocol
    """)
    
    print("\n=== By Protocol ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} events (${row[2]:,.2f} valued)")
    
    # Taxable income events
    cur = conn.execute("""
        SELECT 
            strftime('%Y', datetime(block_timestamp/1000000000, 'unixepoch')) as year,
            protocol,
            SUM(value_usd) as income_usd,
            COUNT(*) as events
        FROM defi_events
        WHERE tax_category = 'income'
        AND block_timestamp IS NOT NULL
        GROUP BY year, protocol
        ORDER BY year, protocol
    """)
    
    print("\n=== Taxable Income by Year ===")
    total_income = 0
    for row in cur.fetchall():
        year, protocol, usd, events = row
        usd = usd or 0
        total_income += usd
        print(f"  {year} - {protocol}: ${usd:,.2f} ({events} events)")
    
    print(f"\n  TOTAL DEFI INCOME: ${total_income:,.2f}")
    
    # Trade events (capital gains)
    cur = conn.execute("""
        SELECT 
            strftime('%Y', datetime(block_timestamp/1000000000, 'unixepoch')) as year,
            COUNT(*) as trades
        FROM defi_events
        WHERE tax_category = 'trade'
        AND block_timestamp IS NOT NULL
        GROUP BY year
        ORDER BY year
    """)
    
    print("\n=== Trades (Need Cost Basis Calculation) ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} trades")
    
    # Items needing review
    cur = conn.execute("""
        SELECT COUNT(*) FROM defi_events WHERE needs_review = 1
    """)
    needs_review = cur.fetchone()[0]
    print(f"\n⚠️  Events needing manual review: {needs_review}")
    
    conn.close()


if __name__ == "__main__":
    print("=" * 70)
    print("NEARTAX DEFI PARSER")
    print("=" * 70)
    
    # Clear and reprocess
    clear_defi_events()
    
    # Parse each protocol
    print("\n--- Parsing Burrow Finance ---")
    parse_burrow_transactions()
    
    print("\n--- Parsing Ref Finance ---")
    parse_ref_transactions()
    
    print("\n--- Parsing Meta Pool ---")
    parse_meta_pool_transactions()
    
    # Summaries
    get_burrow_summary()
    get_ref_summary()
    get_meta_pool_summary()
    
    # Full summary
    get_full_defi_summary()
