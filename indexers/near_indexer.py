#!/usr/bin/env python3
"""Resumable NEAR transaction indexer with progress tracking."""

from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from indexers.nearblocks_client import NearBlocksClient


def get_wallet_id(account_id):
    """Get or create wallet record."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM wallets WHERE account_id = ?", 
        (account_id,)
    ).fetchone()
    
    if row:
        conn.close()
        return row[0]
    
    conn.execute(
        "INSERT INTO wallets (account_id) VALUES (?)", 
        (account_id,)
    )
    conn.commit()
    wallet_id = conn.execute(
        "SELECT id FROM wallets WHERE account_id = ?", 
        (account_id,)
    ).fetchone()[0]
    conn.close()
    return wallet_id


def get_indexing_status(wallet_id):
    """Get current indexing progress."""
    conn = get_connection()
    row = conn.execute(
        """SELECT last_cursor, total_fetched, total_expected, status 
           FROM indexing_progress WHERE wallet_id = ?""",
        (wallet_id,)
    ).fetchone()
    conn.close()
    
    if row:
        return {
            "cursor": row[0],
            "fetched": row[1] or 0,
            "expected": row[2],
            "status": row[3]
        }
    return {"cursor": None, "fetched": 0, "expected": None, "status": "pending"}


def update_progress(wallet_id, cursor, fetched, status, expected=None, error=None):
    """Update indexing progress."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO indexing_progress 
            (wallet_id, last_cursor, total_fetched, total_expected, status, error_message, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(wallet_id) DO UPDATE SET
            last_cursor = excluded.last_cursor,
            total_fetched = excluded.total_fetched,
            total_expected = COALESCE(excluded.total_expected, indexing_progress.total_expected),
            status = excluded.status,
            error_message = excluded.error_message,
            updated_at = CURRENT_TIMESTAMP,
            completed_at = CASE WHEN excluded.status = 'complete' THEN CURRENT_TIMESTAMP ELSE completed_at END
    """, (wallet_id, cursor, fetched, expected, status, error))
    conn.commit()
    conn.close()


def index_account(account_id, force=False, incremental=True):
    """
    Index all transactions for an account.
    
    Resumable - saves cursor after each page.
    If incremental=True and already complete, still checks for new transactions.
    Returns: total transactions indexed
    """
    client = NearBlocksClient()
    wallet_id = get_wallet_id(account_id)
    
    # Check current status
    status = get_indexing_status(wallet_id)
    
    if status["status"] == "complete" and not force:
        if incremental:
            # Check if there are new transactions since last sync
            try:
                current_count = client.get_transaction_count(account_id)
                if current_count <= status["fetched"]:
                    print(f"{account_id}: Already complete, no new txs ({status['fetched']} txs)")
                    return status["fetched"]
                print(f"{account_id}: Found {current_count - status['fetched']} new txs since last sync")
                # Reset to re-fetch (INSERT OR IGNORE handles duplicates)
                status["cursor"] = None
                status["fetched"] = 0
            except Exception as e:
                print(f"{account_id}: Error checking for new txs - {e}")
                return status["fetched"]
        else:
            print(f"{account_id}: Already complete ({status['fetched']} txs)")
            return status["fetched"]
    
    # Get total for progress display
    try:
        total_expected = client.get_transaction_count(account_id)
    except Exception as e:
        print(f"{account_id}: Error getting tx count - {e}")
        total_expected = status.get("expected") or 0
    
    print(f"{account_id}: {total_expected} total transactions")
    
    cursor = status["cursor"]
    fetched = status["fetched"]
    
    # Mark as in progress
    update_progress(wallet_id, cursor, fetched, "in_progress", total_expected)
    
    try:
        while True:
            result = client.fetch_transactions(account_id, cursor=cursor, per_page=25)
            txns = result.get("txns", [])
            
            if not txns:
                break
            
            # Insert transactions
            conn = get_connection()
            for tx in txns:
                # Determine direction
                predecessor = tx.get("predecessor_account_id", "")
                receiver = tx.get("receiver_account_id", "")
                
                if predecessor == account_id:
                    direction = "out"
                    counterparty = receiver
                else:
                    direction = "in"
                    counterparty = predecessor
                
                # Parse actions
                actions = tx.get("actions", [])
                action_type = actions[0].get("action") if actions else None
                method_name = actions[0].get("method") if actions else None
                amount = str(tx.get("actions_agg", {}).get("deposit", 0))
                fee = str(tx.get("outcomes_agg", {}).get("transaction_fee", 0))
                
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO transactions 
                        (tx_hash, receipt_id, wallet_id, direction, counterparty, 
                         action_type, method_name, amount, fee, block_height, 
                         block_timestamp, success, raw_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        tx.get("transaction_hash"),
                        tx.get("receipt_id"),
                        wallet_id,
                        direction,
                        counterparty,
                        action_type,
                        method_name,
                        amount,
                        fee,
                        tx.get("block", {}).get("block_height"),
                        tx.get("block_timestamp"),
                        tx.get("outcomes", {}).get("status", False),
                        str(tx)[:10000]  # Truncate raw JSON
                    ))
                except Exception as e:
                    print(f"  Warning: Error inserting tx: {e}")
            
            conn.commit()
            conn.close()
            
            fetched += len(txns)
            cursor = result.get("cursor")
            
            # Save progress after each page
            update_progress(wallet_id, cursor, fetched, "in_progress", total_expected)
            
            # Progress display
            if total_expected > 0:
                pct = fetched / total_expected * 100
                print(f"  Progress: {fetched}/{total_expected} ({pct:.1f}%)")
            else:
                print(f"  Fetched: {fetched}")
            
            if not cursor:
                break
        
        update_progress(wallet_id, None, fetched, "complete", total_expected)
        print(f"{account_id}: Complete! {fetched} transactions indexed")
        return fetched
        
    except KeyboardInterrupt:
        print(f"\n{account_id}: Interrupted at {fetched} txs. Progress saved.")
        update_progress(wallet_id, cursor, fetched, "in_progress", total_expected)
        raise
    except Exception as e:
        update_progress(wallet_id, cursor, fetched, "error", total_expected, str(e))
        print(f"{account_id}: Error at {fetched} txs - {e}")
        raise


if __name__ == "__main__":
    import sys
    account = sys.argv[1] if len(sys.argv) > 1 else "aaron.near"
    force = "--force" in sys.argv
    
    try:
        count = index_account(account, force=force)
        print(f"\nIndexed {count} transactions")
    except KeyboardInterrupt:
        print("\nInterrupted - progress saved")
