#!/usr/bin/env python3
"""mpDAO Lock/Unlock Tracker

Detects and tracks mpDAO locking events from mpdao-vote.near contract.
Integrates with the NEAR indexer to maintain locked_positions table.
"""

import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import base64
import requests
from db.init import get_connection


def process_mpdao_lock(tx, wallet_id, account_id):
    """
    Detect and process mpDAO lock/unlock events.

    Lock methods: claim_and_lock, bond_mpdao
    Unlock methods: claim_unlocked_mpdao, delegated_claim_unlocked_mpdao

    Updates locked_positions table accordingly.
    """
    receiver = tx.get("receiver_account_id", "")
    predecessor = tx.get("predecessor_account_id", "")

    # Only process mpdao-vote.near contract calls
    if receiver != "mpdao-vote.near":
        return

    # Only process if this wallet initiated the call
    if predecessor != account_id:
        return

    # Check transaction succeeded
    success = tx.get("outcomes", {}).get("status", False)
    if not success:
        return

    actions = tx.get("actions", [])
    if not actions:
        return

    for action in actions:
        method = action.get("method", "")
        args_str = action.get("args", "{}")

        try:
            args = json.loads(args_str) if isinstance(args_str, str) else args_str
        except Exception:
            args = {}

        # LOCK: claim_and_lock or bond_mpdao
        if method in ("claim_and_lock", "bond_mpdao"):
            amount = int(args.get("amount", 0))
            if amount > 0:
                print(f"  [mpDAO] Lock detected: {amount / 1e6:.2f} mpDAO")
                update_locked_position(
                    wallet_id=wallet_id,
                    amount=amount,
                    action="lock"
                )

        # UNLOCK: claim_unlocked_mpdao or delegated_claim_unlocked_mpdao
        elif method in ("claim_unlocked_mpdao", "delegated_claim_unlocked_mpdao"):
            print("  [mpDAO] Unlock detected, refreshing from contract...")
            refresh_locked_position(wallet_id, account_id)


def update_locked_position(wallet_id, amount, action):
    """Update locked_positions table for lock events."""
    conn = get_connection()

    if action == "lock":
        # Check if position exists
        existing = conn.execute(
            "SELECT amount FROM locked_positions WHERE wallet_id = ? AND lock_contract = 'mpdao-vote.near'",
            (wallet_id,)
        ).fetchone()

        if existing:
            # Add to existing
            new_amount = int(existing[0]) + amount
            conn.execute("""
                UPDATE locked_positions
                SET amount = ?, updated_at = CURRENT_TIMESTAMP
                WHERE wallet_id = ? AND lock_contract = 'mpdao-vote.near'
            """, (str(new_amount), wallet_id))
        else:
            # Create new position
            conn.execute("""
                INSERT INTO locked_positions
                    (wallet_id, token_symbol, token_contract, lock_contract, lock_type, amount, decimals, updated_at)
                VALUES (?, 'mpDAO', 'mpdao-token.near', 'mpdao-vote.near', 'governance', ?, 6, CURRENT_TIMESTAMP)
            """, (wallet_id, str(amount)))

    conn.commit()
    conn.close()


def refresh_locked_position(wallet_id, account_id):
    """Refresh locked position from contract state (for unlocks)."""
    try:
        # Query mpdao-vote.near for current locked amount
        resp = requests.post(
            "https://rpc.fastnear.com",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "query",
                "params": {
                    "request_type": "call_function",
                    "finality": "final",
                    "account_id": "mpdao-vote.near",
                    "method_name": "get_user",
                    "args_base64": base64.b64encode(json.dumps({"account_id": account_id}).encode()).decode()
                }
            },
            timeout=10
        )

        if resp.ok:
            result = resp.json().get("result", {})
            if result.get("result"):
                data = json.loads(bytes(result["result"]).decode())
                locked_amount = int(data.get("locking_positions", {}).get("0", {}).get("amount", 0))

                conn = get_connection()
                if locked_amount > 0:
                    conn.execute("""
                        INSERT INTO locked_positions
                            (wallet_id, token_symbol, token_contract, lock_contract, lock_type, amount, decimals, updated_at)
                        VALUES (?, 'mpDAO', 'mpdao-token.near', 'mpdao-vote.near', 'governance', ?, 6, CURRENT_TIMESTAMP)
                        ON CONFLICT(wallet_id, lock_contract) DO UPDATE SET
                            amount = ?,
                            updated_at = CURRENT_TIMESTAMP
                    """, (wallet_id, str(locked_amount), str(locked_amount)))
                else:
                    conn.execute("""
                        DELETE FROM locked_positions
                        WHERE wallet_id = ? AND lock_contract = 'mpdao-vote.near'
                    """, (wallet_id,))
                conn.commit()
                conn.close()
                print(f"  [mpDAO] Updated locked amount to {locked_amount / 1e6:.2f}")
    except Exception as e:
        print(f"  [mpDAO] Error refreshing locked position: {e}")


def sync_all_mpdao_locks(user_id=None):
    """Sync mpDAO locked positions for all wallets (or specific user)."""
    conn = get_connection()

    if user_id:
        wallets = conn.execute(
            "SELECT id, account_id FROM wallets WHERE user_id = ? AND chain = 'NEAR'",
            (user_id,)
        ).fetchall()
    else:
        wallets = conn.execute(
            "SELECT id, account_id FROM wallets WHERE chain = 'NEAR'"
        ).fetchall()

    conn.close()

    print(f"Syncing mpDAO locks for {len(wallets)} wallets...")

    for wallet_id, account_id in wallets:
        try:
            refresh_locked_position(wallet_id, account_id)
        except Exception as e:
            print(f"  Error syncing {account_id}: {e}")

    print("Done.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "--all":
            sync_all_mpdao_locks()
        else:
            # Sync for specific account
            account = sys.argv[1]
            conn = get_connection()
            row = conn.execute("SELECT id FROM wallets WHERE account_id = ?", (account,)).fetchone()
            conn.close()
            if row:
                refresh_locked_position(row[0], account)
            else:
                print(f"Wallet not found: {account}")
    else:
        print("Usage: python mpdao_tracker.py [account_id | --all]")
