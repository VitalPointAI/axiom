#!/usr/bin/env python3
"""
Fix System Deposits Categorization

Problem:
- "system" deposits include both staking rewards AND unstaking returns
- Unstaking returns should NOT be counted as new acquisitions (they're your own NEAR coming back)
- Only actual staking rewards should be taxable income

Solution:
- Large "system" deposits (>10 NEAR) are likely unstaking returns - recategorize as "unstake_return"
- Small "system" deposits are likely staking rewards - keep as income
- Cross-reference with staking_income table for accuracy

Usage:
    python3 fix_system_deposits.py [db_path]
"""

import sqlite3
from datetime import datetime, timezone
import sys

# Thresholds for categorization
# Individual staking rewards are typically small (0.001 - 5 NEAR per day)
# Unstaking returns are typically large (10+ NEAR)
REWARD_THRESHOLD = 10.0  # NEAR - above this is likely unstake return


def fix_system_deposits(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get system deposits
    cur.execute("""
        SELECT id, tx_hash, wallet_id, amount, block_timestamp, tax_category
        FROM transactions
        WHERE direction = 'in' 
        AND counterparty = 'system'
        AND tax_category = 'deposit'
    """)
    
    rows = cur.fetchall()
    print(f"Found {len(rows)} system deposits to analyze")
    
    # Statistics
    total_near = 0
    rewards_near = 0
    returns_near = 0
    recategorized = 0
    
    for row in rows:
        tx_id = row["id"]
        amount_raw = row["amount"]
        
        try:
            amount_near = float(amount_raw) / 1e24
        except:
            continue
        
        total_near += amount_near
        
        # Categorize based on amount
        if amount_near > REWARD_THRESHOLD:
            # Likely an unstake return - not a taxable acquisition
            # Change category to "unstake_return" which shouldn't add to cost pool
            cur.execute("""
                UPDATE transactions 
                SET tax_category = 'unstake_return',
                    category_notes = 'Recategorized from deposit - likely unstaking return (amount > 10 NEAR)'
                WHERE id = ?
            """, (tx_id,))
            returns_near += amount_near
            recategorized += 1
        else:
            # Likely staking reward - taxable income
            cur.execute("""
                UPDATE transactions 
                SET tax_category = 'staking_income',
                    category_notes = 'Recategorized from deposit - likely staking reward (amount <= 10 NEAR)'
                WHERE id = ?
            """, (tx_id,))
            rewards_near += amount_near
    
    conn.commit()
    
    print(f"\nResults:")
    print(f"  Total system deposits: {total_near:,.2f} NEAR")
    print(f"  Recategorized as unstake_return: {returns_near:,.2f} NEAR ({returns_near/total_near*100:.1f}%)")
    print(f"  Recategorized as staking_income: {rewards_near:,.2f} NEAR ({rewards_near/total_near*100:.1f}%)")
    print(f"  Transactions recategorized: {recategorized}")
    
    # Verify the fix
    cur.execute("""
        SELECT tax_category, COUNT(*), SUM(CAST(amount AS REAL) / 1e24) as near
        FROM transactions
        WHERE direction = 'in' AND counterparty = 'system'
        GROUP BY tax_category
    """)
    
    print(f"\nSystem deposits after fix:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} txs, {row[2]:,.2f} NEAR")
    
    return recategorized


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "neartax.db"
    
    print("=" * 60)
    print("Fix System Deposits Categorization")
    print(f"Database: {db_path}")
    print("=" * 60)
    
    fixed = fix_system_deposits(db_path)
    
    print("\n" + "=" * 60)
    print(f"Complete! Fixed {fixed} transactions")
    print("=" * 60)
    print("\nNext step: Re-run ACB calculator to update capital gains")


if __name__ == "__main__":
    main()
