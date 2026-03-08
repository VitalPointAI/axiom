#!/usr/bin/env python3
"""NEAR Transaction Indexer using NearBlocks API

Replaces Pikespeak with NearBlocks for more accurate transaction data.
"""

import json
import sys
import time
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2
from psycopg2.extras import execute_values
import os

# Load API key from .env file
def _load_env_key():
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith('NEARBLOCKS_API_KEY='):
                return line.split('=', 1)[1].strip()
    return ''

NEARBLOCKS_API_KEY = _load_env_key()

PG_CONN = 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'
NEARBLOCKS_API = 'https://api.nearblocks.io/v1'

# Rate limiting - NearBlocks has strict limits
REQUEST_DELAY = 0.5  # seconds between requests

def get_transactions(account_id: str, after_timestamp: Optional[int] = None, limit: int = 25):
    """Fetch transactions from NearBlocks API."""
    url = f"{NEARBLOCKS_API}/account/{account_id}/txns"
    params = {'per_page': limit, 'order': 'desc'}
    
    all_txns = []
    cursor = None
    
    while True:
        if cursor:
            params['cursor'] = cursor
        
        time.sleep(REQUEST_DELAY)  # Rate limit
            
        try:
            resp = requests.get(url, params=params, headers={'Authorization': f'Bearer {NEARBLOCKS_API_KEY}'} if NEARBLOCKS_API_KEY else {}, timeout=30)
            if resp.status_code == 429:
                print(f"  Rate limited, waiting 10s...")
                time.sleep(10)
                continue
            if resp.status_code != 200:
                print(f"  Error {resp.status_code} fetching txns for {account_id}")
                break
                
            data = resp.json()
            txns = data.get('txns', [])
            
            if not txns:
                break
                
            for txn in txns:
                # Check if we've passed our timestamp cutoff
                ts = int(txn.get('block_timestamp', '0'))
                if after_timestamp and ts <= after_timestamp:
                    return all_txns
                all_txns.append(txn)
            
            # Get cursor for next page
            cursor = data.get('cursor')
            if not cursor or len(txns) < limit:
                break
                
        except Exception as e:
            print(f"  Error: {e}")
            break
    
    return all_txns


def get_ft_transfers(account_id: str, after_timestamp: Optional[int] = None, limit: int = 25):
    """Fetch FT token transfers from NearBlocks API."""
    url = f"{NEARBLOCKS_API}/account/{account_id}/ft-txns"
    params = {'per_page': limit, 'order': 'desc'}
    
    all_transfers = []
    cursor = None
    
    while True:
        if cursor:
            params['cursor'] = cursor
        
        time.sleep(REQUEST_DELAY)  # Rate limit
            
        try:
            resp = requests.get(url, params=params, headers={'Authorization': f'Bearer {NEARBLOCKS_API_KEY}'} if NEARBLOCKS_API_KEY else {}, timeout=30)
            if resp.status_code == 429:
                print(f"  Rate limited on FT, waiting 10s...")
                time.sleep(10)
                continue
            if resp.status_code != 200:
                print(f"  Error {resp.status_code} fetching FT txns for {account_id}")
                break
                
            data = resp.json()
            txns = data.get('txns', [])
            
            if not txns:
                break
                
            for txn in txns:
                ts = int(txn.get('block_timestamp', '0'))
                if after_timestamp and ts <= after_timestamp:
                    return all_transfers
                all_transfers.append(txn)
            
            cursor = data.get('cursor')
            if not cursor or len(txns) < limit:
                break
                
        except Exception as e:
            print(f"  Error: {e}")
            break
    
    return all_transfers


def parse_near_transaction(txn: dict, wallet_id: int, account_id: str) -> Optional[dict]:
    """Parse a NearBlocks transaction into our format."""
    try:
        tx_hash = txn.get('transaction_hash')
        block_timestamp = int(txn.get('block_timestamp', '0'))
        predecessor = txn.get('predecessor_account_id', '')
        receiver = txn.get('receiver_account_id', '')
        
        # Determine direction
        if predecessor == account_id:
            direction = 'out'
            counterparty = receiver
        else:
            direction = 'in'
            counterparty = predecessor
        
        # Get amount from actions
        amount = 0
        method_name = None
        
        actions = txn.get('actions', [])
        for action in actions:
            action_type = action.get('action', '')
            if action_type == 'TRANSFER':
                deposit = action.get('deposit', 0)
                if deposit:
                    amount = int(deposit) / 1e24  # Convert yoctoNEAR to NEAR
            elif action_type == 'FUNCTION_CALL':
                method_name = action.get('method')
                deposit = action.get('deposit', 0)
                if deposit:
                    amount = int(deposit) / 1e24
        
        # Skip zero-amount transactions unless they have method calls
        if amount == 0 and not method_name:
            return None
        
        # Get fee
        fee = 0
        outcomes = txn.get('outcomes_agg', {})
        if outcomes.get('transaction_fee'):
            fee = int(outcomes['transaction_fee']) / 1e24
        
        # Auto-categorize
        tax_category = categorize_transaction(direction, counterparty, method_name, account_id)
        
        return {
            'wallet_id': wallet_id,
            'tx_hash': tx_hash,
            'block_timestamp': block_timestamp,
            'direction': direction,
            'amount': amount,
            'fee': fee if direction == 'out' else 0,
            'counterparty': counterparty,
            'method_name': method_name,
            'status': 'success' if txn.get('outcomes', {}).get('status') else 'failed',
            'tax_category': tax_category,
            'needs_review': False if tax_category else True
        }
        
    except Exception as e:
        print(f"  Parse error: {e}")
        return None


def parse_ft_transfer(txn: dict, wallet_id: int, account_id: str) -> Optional[dict]:
    """Parse a FT transfer into our format."""
    try:
        tx_hash = txn.get('transaction_hash') or txn.get('receipt_id')
        block_timestamp = int(txn.get('block_timestamp', '0'))
        
        sender = txn.get('sender_account_id', txn.get('cause_account_id', ''))
        receiver = txn.get('receiver_account_id', txn.get('affected_account_id', ''))
        
        # Determine direction
        if sender == account_id:
            direction = 'out'
            counterparty = receiver
        else:
            direction = 'in'
            counterparty = sender
        
        # Token info
        token_contract = txn.get('contract_account_id', txn.get('ft', {}).get('contract', ''))
        token_symbol = txn.get('ft', {}).get('symbol', token_contract.split('.')[0].upper())
        decimals = int(txn.get('ft', {}).get('decimals', 18))
        
        # Amount
        delta = txn.get('delta_amount', txn.get('amount', '0'))
        amount = abs(int(delta)) / (10 ** decimals)
        
        if amount == 0:
            return None
        
        # Auto-categorize
        tax_category = categorize_ft_transfer(direction, counterparty, token_symbol, account_id)
        
        return {
            'wallet_id': wallet_id,
            'tx_hash': tx_hash,
            'block_timestamp': block_timestamp,
            'direction': direction,
            'token_contract': token_contract,
            'token_symbol': token_symbol,
            'amount': str(amount),
            'counterparty': counterparty,
            'tax_category': tax_category,
            'needs_review': False if tax_category else True
        }
        
    except Exception as e:
        print(f"  FT parse error: {e}")
        return None


def categorize_transaction(direction: str, counterparty: str, method: str, account_id: str) -> Optional[str]:
    """Auto-categorize a NEAR transaction."""
    cp_lower = counterparty.lower() if counterparty else ''
    method_lower = method.lower() if method else ''
    
    # Staking
    if 'pool' in cp_lower or cp_lower.endswith('.poolv1.near'):
        if direction == 'out':
            return 'staking'
        return 'unstaking'
    
    # DeFi protocols
    if 'burrow' in cp_lower or 'ref' in cp_lower:
        return 'defi'
    
    # Swaps
    if 'swap' in method_lower:
        return 'trade'
    
    # Lockup
    if 'lockup' in cp_lower:
        return 'income' if direction == 'in' else 'transfer'
    
    # System (gas refunds)
    if counterparty == 'system':
        return 'fee_refund'
    
    # Internal transfers
    if account_id in cp_lower or cp_lower.endswith('.near'):
        # Could be internal transfer - needs review
        return None
    
    return None


def categorize_ft_transfer(direction: str, counterparty: str, token: str, account_id: str) -> Optional[str]:
    """Auto-categorize a FT transfer."""
    cp_lower = counterparty.lower() if counterparty else ''
    
    # DeFi
    if 'burrow' in cp_lower or 'ref' in cp_lower:
        return 'defi'
    
    # Airdrops (common patterns)
    if direction == 'in' and ('airdrop' in cp_lower or 'claim' in cp_lower):
        return 'income'
    
    return None


def sync_wallet(conn, wallet_id: int, account_id: str, last_sync_timestamp: Optional[int] = None):
    """Sync a single wallet's transactions."""
    cursor = conn.cursor()
    
    print(f"Syncing {account_id}...")
    
    # Get NEAR transactions
    near_txns = get_transactions(account_id, last_sync_timestamp)
    print(f"  Found {len(near_txns)} NEAR transactions")
    
    # Get FT transfers
    ft_txns = get_ft_transfers(account_id, last_sync_timestamp)
    print(f"  Found {len(ft_txns)} FT transfers")
    
    # Parse and insert NEAR transactions
    new_near = 0
    for txn in near_txns:
        parsed = parse_near_transaction(txn, wallet_id, account_id)
        if not parsed:
            continue
            
        # Check for duplicate
        cursor.execute("SELECT 1 FROM transactions WHERE tx_hash = %s AND wallet_id = %s", 
                      (parsed['tx_hash'], wallet_id))
        if cursor.fetchone():
            continue
        
        cursor.execute("""
            INSERT INTO transactions 
            (wallet_id, tx_hash, block_timestamp, direction, amount, fee, counterparty, 
             method_name, status, tax_category, needs_review)
            VALUES (%(wallet_id)s, %(tx_hash)s, %(block_timestamp)s, %(direction)s, %(amount)s,
                    %(fee)s, %(counterparty)s, %(method_name)s, %(status)s, %(tax_category)s, %(needs_review)s)
        """, parsed)
        new_near += 1
    
    # Parse and insert FT transactions
    new_ft = 0
    for txn in ft_txns:
        parsed = parse_ft_transfer(txn, wallet_id, account_id)
        if not parsed:
            continue
            
        # Check for duplicate
        cursor.execute("""
            SELECT 1 FROM ft_transactions 
            WHERE tx_hash = %s AND wallet_id = %s AND token_contract = %s AND direction = %s
        """, (parsed['tx_hash'], wallet_id, parsed['token_contract'], parsed['direction']))
        if cursor.fetchone():
            continue
        
        cursor.execute("""
            INSERT INTO ft_transactions 
            (wallet_id, tx_hash, block_timestamp, direction, token_contract, token_symbol,
             amount, counterparty, tax_category, needs_review)
            VALUES (%(wallet_id)s, %(tx_hash)s, %(block_timestamp)s, %(direction)s, 
                    %(token_contract)s, %(token_symbol)s, %(amount)s, %(counterparty)s,
                    %(tax_category)s, %(needs_review)s)
        """, parsed)
        new_ft += 1
    
    # Update last sync timestamp
    cursor.execute("""
        UPDATE wallets SET last_synced_at = NOW() WHERE id = %s
    """, (wallet_id,))
    
    conn.commit()
    print(f"  Inserted {new_near} NEAR txns, {new_ft} FT transfers")
    
    return new_near, new_ft


def sync_all(user_id: Optional[int] = None):
    """Sync all wallets (or for a specific user)."""
    conn = psycopg2.connect(PG_CONN)
    cursor = conn.cursor()
    
    # Get wallets
    if user_id:
        cursor.execute("SELECT id, account_id FROM wallets WHERE user_id = %s AND chain = 'NEAR'", (user_id,))
    else:
        cursor.execute("SELECT id, account_id FROM wallets WHERE chain = 'NEAR'")
    
    wallets = cursor.fetchall()
    print(f"Syncing {len(wallets)} NEAR wallets...")
    
    total_near = 0
    total_ft = 0
    
    for wallet_id, account_id in wallets:
        try:
            near, ft = sync_wallet(conn, wallet_id, account_id)
            total_near += near
            total_ft += ft
        except Exception as e:
            print(f"  Error syncing {account_id}: {e}")
            conn.rollback()
    
    conn.close()
    print(f"\nTotal: {total_near} NEAR txns, {total_ft} FT transfers")


if __name__ == '__main__':
    import argparse
    from indexer_reporter import IndexerReporter
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', type=int, help='Sync only this user ID')
    args = parser.parse_args()
    
    reporter = IndexerReporter('near_indexer')
    reporter.start()
    
    try:
        sync_all(args.user)
        # Count total records
        conn = psycopg2.connect(PG_CONN)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transactions")
        total = cur.fetchone()[0]
        conn.close()
        reporter.success(records_processed=total)
    except Exception as e:
        reporter.error(str(e))
        raise
