#!/usr/bin/env python3
"""
Wallet graph for detecting owned wallets and internal transfers.

Uses transaction patterns to suggest potentially owned wallets.
"""

from collections import defaultdict
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection


def get_all_owned_addresses():
    """Get all explicitly owned addresses."""
    conn = get_connection()
    
    addresses = set()
    
    # NEAR wallets
    rows = conn.execute(
        "SELECT account_id FROM wallets WHERE is_owned = 1"
    ).fetchall()
    for row in rows:
        addresses.add(('near', row[0].lower()))
    
    # EVM wallets
    rows = conn.execute(
        "SELECT address, chain FROM evm_wallets WHERE is_owned = 1"
    ).fetchall()
    for row in rows:
        addresses.add((row[1], row[0].lower()))
    
    conn.close()
    return addresses


def build_transfer_graph():
    """
    Build a graph of transfers between addresses.
    
    Returns dict: address -> {counterparties: [(address, count, total_amount)]}
    """
    conn = get_connection()
    graph = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'amount': 0}))
    
    # NEAR transactions
    rows = conn.execute("""
        SELECT w.account_id, t.counterparty, t.direction, t.amount
        FROM transactions t
        JOIN wallets w ON t.wallet_id = w.id
        WHERE t.action_type = 'TRANSFER' AND t.amount > 0
    """).fetchall()
    
    for row in rows:
        account = row[0].lower()
        counterparty = (row[1] or '').lower()
        direction = row[2]
        amount = float(row[3] or 0)
        
        if counterparty:
            if direction == 'out':
                graph[account][counterparty]['count'] += 1
                graph[account][counterparty]['amount'] += amount
            else:
                graph[counterparty][account]['count'] += 1
                graph[counterparty][account]['amount'] += amount
    
    conn.close()
    return graph


def find_potential_owned_wallets(min_transfers=3, min_amount=1e24):
    """
    Find addresses that might be owned based on transfer patterns.
    
    Looks for:
    - Addresses with multiple transfers to/from owned wallets
    - Large amounts transferred
    
    Returns list of potential addresses with confidence scores.
    """
    owned = get_all_owned_addresses()
    owned_near = {addr for chain, addr in owned if chain == 'near'}
    
    graph = build_transfer_graph()
    
    potential = []
    
    # Find addresses with significant interaction with owned wallets
    for owned_addr in owned_near:
        if owned_addr not in graph:
            continue
        
        for counterparty, stats in graph[owned_addr].items():
            if counterparty in owned_near:
                continue  # Already owned
            
            count = stats['count']
            amount = stats['amount']
            
            if count >= min_transfers or amount >= min_amount:
                # Calculate confidence based on interaction patterns
                confidence = min(100, (count * 10) + (amount / 1e24))
                
                potential.append({
                    'address': counterparty,
                    'related_to': owned_addr,
                    'transfer_count': count,
                    'total_amount': amount / 1e24,
                    'confidence': confidence
                })
    
    # Sort by confidence
    potential.sort(key=lambda x: x['confidence'], reverse=True)
    
    return potential


def is_internal_transfer(from_addr, to_addr):
    """
    Check if a transfer is between owned wallets.
    """
    owned = get_all_owned_addresses()
    
    # Check both NEAR and EVM
    from_owned = any(
        from_addr.lower() == addr 
        for chain, addr in owned
    )
    to_owned = any(
        to_addr.lower() == addr 
        for chain, addr in owned
    )
    
    return from_owned and to_owned


def get_internal_transfer_summary():
    """Get summary of internal transfers."""
    conn = get_connection()
    owned = get_all_owned_addresses()
    owned_near = {addr for chain, addr in owned if chain == 'near'}
    
    internal_count = 0
    internal_amount = 0
    external_count = 0
    external_amount = 0
    
    rows = conn.execute("""
        SELECT w.account_id, t.counterparty, t.amount
        FROM transactions t
        JOIN wallets w ON t.wallet_id = w.id
        WHERE t.action_type = 'TRANSFER' AND t.direction = 'out'
    """).fetchall()
    
    for row in rows:
        account = row[0].lower()
        counterparty = (row[1] or '').lower()
        amount = float(row[2] or 0) / 1e24
        
        if counterparty in owned_near:
            internal_count += 1
            internal_amount += amount
        else:
            external_count += 1
            external_amount += amount
    
    conn.close()
    
    return {
        'internal_transfers': internal_count,
        'internal_amount': internal_amount,
        'external_transfers': external_count,
        'external_amount': external_amount
    }


if __name__ == "__main__":
    print("Owned Addresses:")
    owned = get_all_owned_addresses()
    print(f"  Total: {len(owned)}")
    
    print("\nInternal Transfer Summary:")
    summary = get_internal_transfer_summary()
    print(f"  Internal: {summary['internal_transfers']} transfers, {summary['internal_amount']:.2f} NEAR")
    print(f"  External: {summary['external_transfers']} transfers, {summary['external_amount']:.2f} NEAR")
    
    print("\nPotential Owned Wallets (not in list):")
    potential = find_potential_owned_wallets()
    for p in potential[:10]:
        print(f"  {p['address'][:30]}... - {p['transfer_count']} transfers, {p['total_amount']:.2f} NEAR")
