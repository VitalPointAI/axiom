#!/usr/bin/env python3
"""Re-sync CDAO wallets that are missing transactions."""

import requests
import sqlite3
import time
import json

DB_PATH = '/home/deploy/neartax/neartax.db'
NEARBLOCKS_API_KEY = '0F1F6973-25FF-4A9E-B8CF-7E33C2199BA6'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_all_txns(account_id):
    """Fetch ALL transactions from NearBlocks for an account."""
    base_url = f'https://api.nearblocks.io/v1/account/{account_id}/txns'
    headers = {'Authorization': f'Bearer {NEARBLOCKS_API_KEY}'}
    
    all_txns = []
    cursor = None
    page = 0
    
    while True:
        params = {'per_page': 25}
        if cursor:
            params['cursor'] = cursor
        
        resp = requests.get(base_url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"Error {resp.status_code}: {resp.text}")
            break
        
        data = resp.json()
        txns = data.get('txns', [])
        if not txns:
            break
        
        all_txns.extend(txns)
        cursor = data.get('cursor')
        page += 1
        print(f"  Page {page}: fetched {len(txns)} txns, total: {len(all_txns)}")
        
        if not cursor:
            break
        
        time.sleep(0.1)  # Rate limit
    
    return all_txns

def parse_transaction(tx, account_id, wallet_id):
    """Parse a NearBlocks transaction into database records."""
    records = []
    
    tx_hash = tx.get('transaction_hash')
    receipt_id = tx.get('receipt_id')
    block_timestamp = tx.get('block_timestamp')
    block_height = tx.get('block', {}).get('block_height')
    
    # Check if receipt failed
    receipt_outcome = tx.get('receipt_outcome', {})
    if receipt_outcome and receipt_outcome.get('status') is False:
        return []  # Skip failed receipts
    
    # Check if tx outcomes show failure
    outcomes = tx.get('outcomes', {})
    if outcomes and outcomes.get('status') is False:
        return []  # Skip failed txs
    
    predecessor = tx.get('predecessor_account_id', '')
    receiver = tx.get('receiver_account_id', '')
    
    actions = tx.get('actions', [])
    tx.get('actions_agg', {})
    
    # Calculate fee (from outcomes_agg)
    outcomes_agg = tx.get('outcomes_agg', {})
    fee = 0
    if outcomes_agg:
        gas_burnt = outcomes_agg.get('transaction_fee', '0')
        fee = int(gas_burnt)
    
    # Process each action
    for action in actions:
        action_type = action.get('action', 'UNKNOWN')
        method_name = action.get('method', None)
        
        # Get deposit amount
        amount = 0
        if action_type == 'TRANSFER':
            amount = int(action.get('deposit', '0'))
        elif action_type == 'FUNCTION_CALL':
            deposit = action.get('deposit', '0')
            if deposit:
                amount = int(deposit)
        elif action_type == 'CREATE_ACCOUNT':
            # Initial funding comes with a TRANSFER action usually
            pass
        elif action_type == 'DELETE_ACCOUNT':
            # Special case: money goes to beneficiary
            beneficiary = action.get('beneficiary_id', '')
            if beneficiary and account_id != beneficiary:
                # This account deleted, money went to beneficiary
                # We need to record this as an OUT
                pass
        
        # Determine direction and counterparty
        if predecessor == account_id:
            # We sent this transaction
            direction = 'out'
            counterparty = receiver
        elif receiver == account_id:
            # We received this
            direction = 'in'
            counterparty = predecessor
        else:
            # Might be from an internal receipt
            continue
        
        # Skip zero-amount non-transfer actions
        if amount == 0 and action_type not in ['CREATE_ACCOUNT', 'DELETE_ACCOUNT']:
            continue
        
        record = {
            'tx_hash': tx_hash,
            'receipt_id': receipt_id,
            'wallet_id': wallet_id,
            'direction': direction,
            'counterparty': counterparty,
            'action_type': action_type,
            'method_name': method_name,
            'amount': amount,
            'fee': fee if direction == 'out' else 0,
            'block_height': block_height,
            'block_timestamp': block_timestamp,
            'success': 1,
            'raw_json': json.dumps(tx)
        }
        records.append(record)
    
    return records

def sync_wallet(account_id):
    """Sync all transactions for a wallet."""
    conn = get_db()
    c = conn.cursor()
    
    # Get wallet_id
    c.execute('SELECT id FROM wallets WHERE account_id = ?', (account_id,))
    row = c.fetchone()
    if not row:
        print(f"Wallet not found: {account_id}")
        return 0
    wallet_id = row['id']
    
    # Get existing tx hashes
    c.execute('SELECT DISTINCT tx_hash FROM transactions WHERE wallet_id = ?', (wallet_id,))
    existing = set(r['tx_hash'] for r in c.fetchall())
    print(f"{account_id}: {len(existing)} existing transactions")
    
    # Fetch all from NearBlocks
    print("Fetching from NearBlocks...")
    all_txns = fetch_all_txns(account_id)
    print(f"  Got {len(all_txns)} total transactions")
    
    # Find missing ones
    new_count = 0
    for tx in all_txns:
        tx_hash = tx.get('transaction_hash')
        if tx_hash in existing:
            continue
        
        # Parse and insert
        records = parse_transaction(tx, account_id, wallet_id)
        for record in records:
            try:
                c.execute("""
                    INSERT OR IGNORE INTO transactions 
                    (tx_hash, receipt_id, wallet_id, direction, counterparty, 
                     action_type, method_name, amount, fee, block_height, 
                     block_timestamp, success, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record['tx_hash'],
                    record['receipt_id'],
                    record['wallet_id'],
                    record['direction'],
                    record['counterparty'],
                    record['action_type'],
                    record['method_name'],
                    record['amount'],
                    record['fee'],
                    record['block_height'],
                    record['block_timestamp'],
                    record['success'],
                    record['raw_json']
                ))
                new_count += 1
            except Exception as e:
                print(f"  Error inserting: {e}")
    
    conn.commit()
    conn.close()
    
    return new_count

if __name__ == '__main__':
    wallets = ['vpacademy.cdao.near', 'vpointai.cdao.near']
    
    for wallet in wallets:
        print(f"\n=== Syncing {wallet} ===")
        new = sync_wallet(wallet)
        print(f"  Added {new} new transactions")
