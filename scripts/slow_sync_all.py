#!/usr/bin/env python3
"""
Slow, conservative sync of all wallets.
Designed to avoid rate limits by being very patient.
"""

import time
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from indexers.near_indexer import index_account
from config import INTER_WALLET_DELAY

def get_wallets_to_sync():
    """Get all wallets that need syncing (error, idle, or pending status)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, account_id, sync_status, last_synced_at
        FROM wallets
        WHERE chain = 'NEAR'
          AND (sync_status IN ('error', 'idle', 'pending', 'in_progress')
               OR sync_status IS NULL)
        ORDER BY
            CASE sync_status
                WHEN 'in_progress' THEN 1
                WHEN 'error' THEN 2
                WHEN 'pending' THEN 3
                ELSE 4
            END,
            id
    """).fetchall()
    conn.close()
    return rows

def update_wallet_status(wallet_id, status, error=None):
    """Update wallet sync status."""
    conn = get_connection()
    if status == 'complete':
        conn.execute("""
            UPDATE wallets
            SET sync_status = 'complete', last_synced_at = datetime('now')
            WHERE id = ?
        """, (wallet_id,))
    else:
        conn.execute("""
            UPDATE wallets SET sync_status = ? WHERE id = ?
        """, (status, wallet_id))
    conn.commit()
    conn.close()

def slow_sync_all():
    """Sync all pending wallets, one at a time, with generous delays."""
    wallets = get_wallets_to_sync()

    if not wallets:
        print("✅ All wallets are already synced!")
        return

    print(f"📋 Found {len(wallets)} wallets to sync")
    print(f"⏱️  Using {INTER_WALLET_DELAY}s delay between wallets")
    print(f"⏱️  Estimated time: {len(wallets) * 2} minutes (varies by tx count)")
    print()

    synced = 0
    errors = 0

    for i, (wallet_id, account_id, status, last_synced) in enumerate(wallets, 1):
        print(f"[{i}/{len(wallets)}] Syncing {account_id}...")

        try:
            update_wallet_status(wallet_id, 'in_progress')
            tx_count = index_account(account_id, force=False, incremental=True)
            update_wallet_status(wallet_id, 'complete')
            synced += 1
            print(f"  ✅ Complete: {tx_count} transactions")
        except KeyboardInterrupt:
            print("\n⚠️  Interrupted! Progress saved.")
            update_wallet_status(wallet_id, 'in_progress')
            break
        except Exception as e:
            errors += 1
            update_wallet_status(wallet_id, 'error')
            print(f"  ❌ Error: {e}")

        # Wait between wallets (unless last one)
        if i < len(wallets):
            print(f"  ⏳ Waiting {INTER_WALLET_DELAY}s before next wallet...")
            time.sleep(INTER_WALLET_DELAY)

    print()
    print("📊 Summary:")
    print(f"  ✅ Synced: {synced}")
    print(f"  ❌ Errors: {errors}")
    print(f"  ⏳ Remaining: {len(wallets) - synced - errors}")

if __name__ == "__main__":
    print("🐢 NearTax Slow Sync - Starting...")
    print("=" * 50)
    slow_sync_all()
