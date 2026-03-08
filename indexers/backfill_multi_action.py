#!/usr/bin/env python3
"""
Backfill missing TRANSFER actions from multi-action transactions.

Finds transactions where CREATE_ACCOUNT has 0 amount but the transaction
actually had a TRANSFER action with the initial funding.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from db.init import get_connection
from indexers.nearblocks_client import NearBlocksClient


def find_zero_create_accounts():
    """Find CREATE_ACCOUNT transactions with 0 amount."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT t.id, t.tx_hash, t.wallet_id, t.counterparty, t.block_timestamp,
               w.account_id
        FROM transactions t
        JOIN wallets w ON t.wallet_id = w.id
        WHERE t.action_type = 'CREATE_ACCOUNT' 
          AND t.direction = 'in'
          AND CAST(t.amount AS REAL) = 0
          AND t.counterparty = 'near'
    """).fetchall()
    conn.close()
    return rows


def fetch_tx_from_nearblocks(tx_hash):
    """Fetch full transaction details from NearBlocks."""
    client = NearBlocksClient()
    try:
        result = client._request(f"v1/txns/{tx_hash}")
        return result.get("txns", [{}])[0] if result.get("txns") else None
    except Exception as e:
        print(f"  Error fetching {tx_hash}: {e}")
        return None


def backfill_missing_transfers():
    """Find and add missing TRANSFER actions from multi-action transactions."""
    zero_creates = find_zero_create_accounts()
    print(f"Found {len(zero_creates)} CREATE_ACCOUNT transactions with 0 amount")
    
    conn = get_connection()
    added = 0
    
    for row in zero_creates:
        tx_id, tx_hash, wallet_id, counterparty, block_timestamp, account_id = row
        print(f"\nChecking {account_id} (tx: {tx_hash[:20]}...)")
        
        # Fetch full transaction from NearBlocks
        tx = fetch_tx_from_nearblocks(tx_hash)
        if not tx:
            print(f"  Could not fetch transaction")
            continue
        
        actions = tx.get("actions", [])
        print(f"  Found {len(actions)} actions: {[a.get('action') for a in actions]}")
        
        # Look for TRANSFER actions with deposits
        for idx, action in enumerate(actions):
            action_type = action.get("action")
            deposit = action.get("deposit", 0)
            
            if action_type == "TRANSFER" and deposit and int(deposit) > 0:
                # Check if this TRANSFER is already recorded
                existing = conn.execute("""
                    SELECT id FROM transactions 
                    WHERE wallet_id = ? AND tx_hash = ? AND action_type = 'TRANSFER'
                """, (wallet_id, tx_hash)).fetchone()
                
                if existing:
                    print(f"  TRANSFER already exists")
                    continue
                
                # Add the missing TRANSFER
                near_amount = int(deposit) / 1e24
                print(f"  Adding missing TRANSFER: {near_amount:.4f} NEAR")
                
                conn.execute("""
                    INSERT INTO transactions 
                    (tx_hash, receipt_id, wallet_id, direction, counterparty, 
                     action_type, method_name, amount, fee, block_height, 
                     block_timestamp, success)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tx_hash,
                    f"{tx.get('receipt_id', '')}_{idx}",  # Unique receipt ID
                    wallet_id,
                    "in",  # Receiving the transfer
                    counterparty,
                    "TRANSFER",
                    None,
                    str(deposit),
                    "0",  # Fee already accounted for in CREATE_ACCOUNT
                    tx.get("block", {}).get("block_height"),
                    block_timestamp,
                    True
                ))
                added += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Added {added} missing TRANSFER records")
    return added


if __name__ == "__main__":
    backfill_missing_transfers()
