#!/usr/bin/env python3
"""Balance reconciliation - compare calculated vs on-chain balance."""

import requests
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import FASTNEAR_RPC
from db.init import get_connection
from indexers.near_indexer import get_wallet_id


def get_onchain_balance(account_id):
    """Get current NEAR balance via FastNear RPC."""
    try:
        response = requests.post(
            FASTNEAR_RPC,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "query",
                "params": {
                    "request_type": "view_account",
                    "finality": "final",
                    "account_id": account_id
                }
            },
            timeout=10
        )
        result = response.json().get("result", {})
        amount = int(result.get("amount", 0))
        return amount / 1e24  # Convert yoctoNEAR to NEAR
    except Exception as e:
        print(f"Error getting on-chain balance: {e}")
        return None


def get_transaction_stats(account_id):
    """Get transaction statistics from indexed data."""
    conn = get_connection()
    wallet_id = get_wallet_id(account_id)
    
    # Count transactions
    total = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE wallet_id = ?",
        (wallet_id,)
    ).fetchone()[0]
    
    # Sum incoming transfers
    incoming = conn.execute("""
        SELECT COUNT(*), COALESCE(SUM(CAST(amount AS REAL)), 0)
        FROM transactions 
        WHERE wallet_id = ? AND direction = 'in' AND action_type = 'TRANSFER'
    """, (wallet_id,)).fetchone()
    
    # Sum outgoing transfers + fees
    outgoing = conn.execute("""
        SELECT COUNT(*), 
               COALESCE(SUM(CAST(amount AS REAL)), 0),
               COALESCE(SUM(CAST(fee AS REAL)), 0)
        FROM transactions 
        WHERE wallet_id = ? AND direction = 'out'
    """, (wallet_id,)).fetchone()
    
    conn.close()
    
    return {
        "total_txs": total,
        "incoming_count": incoming[0],
        "incoming_amount": incoming[1] / 1e24 if incoming[1] else 0,
        "outgoing_count": outgoing[0],
        "outgoing_amount": outgoing[1] / 1e24 if outgoing[1] else 0,
        "fees_paid": outgoing[2] / 1e24 if outgoing[2] else 0
    }


def reconcile_account(account_id):
    """
    Compare calculated vs on-chain balance.
    
    Note: Full reconciliation requires transaction classification to properly
    account for staking, storage deposits, etc. This is initial verification.
    """
    onchain = get_onchain_balance(account_id)
    stats = get_transaction_stats(account_id)
    
    # Simple calculation (won't match due to staking, storage, etc)
    calculated = stats["incoming_amount"] - stats["outgoing_amount"] - stats["fees_paid"]
    
    return {
        "account_id": account_id,
        "onchain_balance": onchain,
        "stats": stats,
        "calculated_net": calculated,
        "difference": abs(onchain - calculated) if onchain else None,
        "note": "Difference expected - staking/storage not yet accounted for. See Phase 3."
    }


def print_reconciliation(result):
    """Pretty print reconciliation result."""
    print(f"\n{'='*50}")
    print(f"RECONCILIATION: {result['account_id']}")
    print(f"{'='*50}")
    
    stats = result['stats']
    print(f"\nIndexed Transactions: {stats['total_txs']:,}")
    print(f"  Incoming: {stats['incoming_count']:,} txs = {stats['incoming_amount']:.4f} NEAR")
    print(f"  Outgoing: {stats['outgoing_count']:,} txs = {stats['outgoing_amount']:.4f} NEAR")
    print(f"  Fees:     {stats['fees_paid']:.4f} NEAR")
    
    print(f"\nBalance Comparison:")
    print(f"  On-chain:   {result['onchain_balance']:.4f} NEAR")
    print(f"  Calculated: {result['calculated_net']:.4f} NEAR")
    if result['difference']:
        print(f"  Difference: {result['difference']:.4f} NEAR")
    
    print(f"\nNote: {result['note']}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    account = sys.argv[1] if len(sys.argv) > 1 else "aaron.near"
    result = reconcile_account(account)
    print_reconciliation(result)
