#!/usr/bin/env python3
"""Clear and re-index CDAO wallets with corrected fee attribution."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from indexers.near_indexer import index_account

wallets = ["vpacademy.cdao.near", "vpointai.cdao.near"]

conn = get_connection()

for wallet in wallets:
    print(f"\n{'='*60}")
    print(f"Re-indexing {wallet}")
    print(f"{'='*60}")

    # Get wallet ID
    row = conn.execute("SELECT id FROM wallets WHERE account_id = ?", (wallet,)).fetchone()
    if not row:
        print(f"  Wallet not found: {wallet}")
        continue
    wallet_id = row[0]

    # Count existing transactions
    count = conn.execute("SELECT COUNT(*) FROM transactions WHERE wallet_id = ?", (wallet_id,)).fetchone()[0]
    print(f"  Clearing {count} existing transactions...")

    # Clear existing transactions
    conn.execute("DELETE FROM transactions WHERE wallet_id = ?", (wallet_id,))

    # Reset indexing progress
    conn.execute("DELETE FROM indexing_progress WHERE wallet_id = ?", (wallet_id,))

    conn.commit()
    print("  Cleared. Re-indexing...")

conn.close()

# Re-index each wallet
for wallet in wallets:
    print(f"\n--- Indexing {wallet} ---")
    try:
        count = index_account(wallet, force=True)
        print(f"  Done: {count} transactions")
    except Exception as e:
        print(f"  Error: {e}")

print("\n" + "="*60)
print("Re-indexing complete!")
