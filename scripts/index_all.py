#!/usr/bin/env python3
"""CLI for batch indexing NEAR transactions."""

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from indexers.near_indexer import index_account, get_wallet_id, get_indexing_status


def get_all_wallets():
    """Get all wallets ordered by account_id."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT account_id FROM wallets ORDER BY account_id"
    ).fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_status_summary():
    """Get indexing status summary."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT status, COUNT(*), SUM(total_fetched)
        FROM indexing_progress 
        GROUP BY status
    """).fetchall()
    conn.close()
    
    summary = {}
    for row in rows:
        summary[row[0] or 'unknown'] = {
            'count': row[1],
            'transactions': row[2] or 0
        }
    return summary


def print_status():
    """Print detailed status."""
    summary = get_status_summary()
    
    print("\n" + "="*50)
    print("INDEXING STATUS")
    print("="*50)
    
    total_wallets = sum(s['count'] for s in summary.values())
    total_txs = sum(s['transactions'] for s in summary.values())
    
    for status, data in sorted(summary.items()):
        print(f"  {status:12}: {data['count']:3} wallets, {data['transactions']:,} txs")
    
    print("-"*50)
    print(f"  {'TOTAL':12}: {total_wallets:3} wallets, {total_txs:,} txs")
    print("="*50 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Index NEAR transactions for all wallets"
    )
    parser.add_argument(
        "--account", 
        help="Index single account"
    )
    parser.add_argument(
        "--status", 
        action="store_true", 
        help="Show status only"
    )
    parser.add_argument(
        "--force", 
        action="store_true", 
        help="Re-index complete accounts"
    )
    parser.add_argument(
        "--limit", 
        type=int, 
        help="Max accounts to process"
    )
    parser.add_argument(
        "--skip-errors",
        action="store_true",
        help="Continue on errors (don't stop)"
    )
    
    args = parser.parse_args()
    
    if args.status:
        print_status()
        return
    
    if args.account:
        try:
            index_account(args.account, force=args.force)
        except KeyboardInterrupt:
            print("\nInterrupted - progress saved")
        return
    
    # Batch mode - index all pending/error accounts
    wallets = get_all_wallets()
    processed = 0
    errors = 0
    
    print(f"\nBatch indexing {len(wallets)} wallets")
    print(f"Limit: {args.limit or 'none'}")
    print(f"Force: {args.force}")
    print()
    
    for i, account_id in enumerate(wallets):
        wallet_id = get_wallet_id(account_id)
        status = get_indexing_status(wallet_id)
        
        # Skip complete unless force
        if status["status"] == "complete" and not args.force:
            continue
        
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(wallets)}] Processing: {account_id}")
        print(f"{'='*60}")
        
        try:
            index_account(account_id, force=args.force)
            processed += 1
        except KeyboardInterrupt:
            print("\n\nInterrupted! Progress saved. Run again to resume.")
            break
        except Exception as e:
            errors += 1
            print(f"Error: {e}")
            if not args.skip_errors:
                print("Use --skip-errors to continue despite errors")
                break
        
        if args.limit and processed >= args.limit:
            print(f"\nLimit reached ({args.limit} accounts)")
            break
    
    print(f"\n{'='*60}")
    print("BATCH COMPLETE")
    print(f"  Processed: {processed}")
    print(f"  Errors: {errors}")
    print(f"{'='*60}")
    
    print_status()


if __name__ == "__main__":
    main()
