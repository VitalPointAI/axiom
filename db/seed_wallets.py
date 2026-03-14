#!/usr/bin/env python3
"""Seed wallets from wallets.json into database."""

import json
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import init_db, get_connection


def seed_wallets():
    """Load wallets from wallets.json and insert into database."""
    
    # Initialize database first
    init_db()
    
    # Load wallets.json
    wallets_file = PROJECT_ROOT / "wallets.json"
    with open(wallets_file, 'r') as f:
        data = json.load(f)
    
    near_accounts = data.get("near", [])
    
    conn = get_connection()
    inserted = 0
    skipped = 0
    
    for account_id in near_accounts:
        try:
            # Insert wallet (ignore if exists)
            conn.execute(
                "INSERT OR IGNORE INTO wallets (account_id) VALUES (?)",
                (account_id,)
            )
            
            # Check if inserted or already existed
            cursor = conn.execute(
                "SELECT id FROM wallets WHERE account_id = ?",
                (account_id,)
            )
            wallet_id = cursor.fetchone()[0]
            
            # Create indexing_progress entry if not exists
            conn.execute("""
                INSERT OR IGNORE INTO indexing_progress 
                (wallet_id, status, total_fetched) 
                VALUES (?, 'pending', 0)
            """, (wallet_id,))
            
            inserted += 1
        except Exception as e:
            print(f"Error inserting {account_id}: {e}")
            skipped += 1
    
    conn.commit()
    
    # Get counts
    wallet_count = conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0]
    pending_count = conn.execute(
        "SELECT COUNT(*) FROM indexing_progress WHERE status = 'pending'"
    ).fetchone()[0]
    
    conn.close()
    
    print("\nSeeding complete:")
    print(f"  Processed: {inserted + skipped}")
    print(f"  Inserted/Updated: {inserted}")
    print(f"  Skipped (errors): {skipped}")
    print("\nDatabase status:")
    print(f"  Total wallets: {wallet_count}")
    print(f"  Pending indexing: {pending_count}")
    
    return wallet_count


if __name__ == "__main__":
    seed_wallets()
