#!/usr/bin/env python3
"""
Backfill missing receipt-level transfers for contract wallets.

When contracts execute code that sends NEAR (Promise::transfer),
those transfers show up as receipts, not top-level transactions.
This script fetches and indexes those receipts.
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from indexers.nearblocks_client import NearBlocksClient

# Contracts that need receipt backfill
CONTRACT_PATTERNS = [
    '.credz.near',
    '.isnft.near',
    '.cdao.near',
]

def is_contract(account):
    return any(p in account for p in CONTRACT_PATTERNS)

def get_contract_wallets():
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, account_id FROM wallets
        WHERE chain = 'NEAR'
    """).fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows if is_contract(r[1])]

def backfill_receipts(wallet_id, account_id, client):
    """Fetch receipts and add missing outbound transfers."""
    conn = get_connection()
    added = 0
    cursor = None

    while True:
        result = client.fetch_receipts(account_id, cursor=cursor, per_page=100)
        receipts = result.get('txns', [])
        if not receipts:
            break

        for r in receipts:
            # Only interested in receipts where this account initiated a transfer
            if r.get('predecessor_account_id') != account_id:
                continue

            actions = r.get('actions', [])
            for action in actions:
                if action.get('action') != 'TRANSFER':
                    continue

                deposit = action.get('deposit', 0)
                if not deposit or float(deposit) < 1e18:  # Skip tiny amounts
                    continue

                tx_hash = r.get('transaction_hash', '')
                receipt_id = r.get('receipt_id', '')
                receiver = r.get('receiver_account_id', '')

                # Check if we already have this receipt
                existing = conn.execute(
                    "SELECT 1 FROM transactions WHERE wallet_id = ? AND receipt_id = ?",
                    (wallet_id, receipt_id)
                ).fetchone()

                if existing:
                    continue

                # Insert the missing transfer
                conn.execute("""
                    INSERT INTO transactions
                    (tx_hash, receipt_id, wallet_id, direction, counterparty,
                     action_type, amount, fee, block_height, timestamp)
                    VALUES (?, ?, ?, 'out', ?, 'TRANSFER', ?, 0, ?, ?)
                """, (
                    tx_hash,
                    receipt_id,
                    wallet_id,
                    receiver,
                    str(int(float(deposit))),
                    r.get('receipt_block', {}).get('block_height', 0),
                    r.get('block_timestamp', '')
                ))
                added += 1

        cursor = result.get('cursor')
        if not cursor:
            break

    conn.commit()
    conn.close()
    return added

def main():
    client = NearBlocksClient()
    contracts = get_contract_wallets()

    print(f"Found {len(contracts)} contract wallets to backfill")

    total_added = 0
    for wallet_id, account_id in contracts:
        print(f"\nBackfilling {account_id}...")
        added = backfill_receipts(wallet_id, account_id, client)
        print(f"  Added {added} missing receipts")
        total_added += added

    print(f"\nTotal added: {total_added} receipts")

if __name__ == '__main__':
    main()
