#!/usr/bin/env python3
"""Categorize all transactions for tax purposes."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from tax.categories import categorize_near_transaction, TaxCategory


def add_category_columns():
    """Add tax category columns to transactions table."""
    conn = get_connection()
    
    columns = [
        ("tax_category", "TEXT"),
        ("category_confidence", "REAL"),
        ("category_notes", "TEXT"),
        ("needs_review", "INTEGER DEFAULT 0"),
    ]
    
    for col_name, col_type in columns:
        try:
            conn.execute(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_type}")
            print(f"Added column: {col_name}")
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                print(f"Warning: {e}")
    
    conn.commit()
    conn.close()


def get_user_wallets():
    """Get all wallet addresses belonging to the user."""
    conn = get_connection()
    rows = conn.execute("SELECT account_id FROM wallets").fetchall()
    conn.close()
    return set(row[0] for row in rows)


def categorize_all(batch_size: int = 500):
    """Categorize all transactions in the database."""
    add_category_columns()
    
    # Get user's own wallets for transfer detection
    own_wallets = get_user_wallets()
    print(f"User has {len(own_wallets)} wallets")
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Get all transactions
    cur.execute("""
        SELECT id, action_type, method_name, counterparty, direction, amount
        FROM transactions
        ORDER BY block_timestamp
    """)
    
    rows = cur.fetchall()
    total = len(rows)
    print(f"Categorizing {total} transactions...")
    
    stats = {}
    needs_review_count = 0
    
    for i, (tx_id, action_type, method_name, counterparty, direction, amount) in enumerate(rows):
        # Check if counterparty is user's own wallet
        is_own = counterparty in own_wallets if counterparty else False
        
        # Convert amount
        try:
            amt = int(amount) if amount else 0
        except (ValueError, TypeError):
            amt = 0
        
        # Categorize
        result = categorize_near_transaction(
            action_type=action_type or "",
            method_name=method_name,
            counterparty=counterparty or "",
            direction=direction or "out",
            amount=amt,
            is_own_wallet=is_own,
        )
        
        # Update database
        conn.execute("""
            UPDATE transactions 
            SET tax_category = ?,
                category_confidence = ?,
                category_notes = ?,
                needs_review = ?
            WHERE id = ?
        """, (
            result.category.value,
            result.confidence,
            result.notes,
            1 if result.needs_review else 0,
            tx_id
        ))
        
        # Track stats
        cat = result.category.value
        stats[cat] = stats.get(cat, 0) + 1
        if result.needs_review:
            needs_review_count += 1
        
        if (i + 1) % batch_size == 0:
            conn.commit()
            print(f"  Progress: {i+1}/{total}")
    
    conn.commit()
    conn.close()
    
    # Print summary
    print(f"\n=== Categorization Complete ===")
    print(f"Total: {total} transactions")
    print(f"Needs review: {needs_review_count}")
    print(f"\nBy category:")
    for cat, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    categorize_all()
