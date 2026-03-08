#!/usr/bin/env python3
"""Backfill staking_events table from NearBlocks API for accurate historical tracking."""

import os
import requests
import psycopg2
from datetime import datetime

# Config
DB_URL = os.environ.get('DATABASE_URL', 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax')
NEARBLOCKS_API_KEY = os.environ.get('NEARBLOCKS_API_KEY', '0F1F69733B684BD48753570B3B9C4B27')

def get_user_wallets(conn, user_id=3):
    """Get all wallet account IDs for a user."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, account_id FROM wallets WHERE user_id = %s", (user_id,))
        return {row[1]: row[0] for row in cur.fetchall()}  # account_id -> wallet_id

def get_staking_positions(conn):
    """Get all validator pools from staking_positions."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT validator FROM staking_positions")
        return [row[0] for row in cur.fetchall()]

def fetch_staking_txns(pool_id, method='deposit_and_stake', max_pages=10):
    """Fetch all staking transactions for a pool from NearBlocks."""
    all_txns = []
    page = 1
    
    while page <= max_pages:
        url = f"https://api.nearblocks.io/v1/account/{pool_id}/txns"
        params = {
            'method': method,
            'per_page': 100,
            'page': page
        }
        headers = {'Authorization': f'Bearer {NEARBLOCKS_API_KEY}'}
        
        try:
            res = requests.get(url, params=params, headers=headers, timeout=30)
            data = res.json()
            txns = data.get('txns', [])
            if not txns:
                break
            all_txns.extend(txns)
            page += 1
        except Exception as e:
            print(f"  Error fetching page {page}: {e}")
            break
    
    return all_txns

def insert_staking_event(conn, wallet_id, validator_id, event_type, amount, tx_hash, block_timestamp):
    """Insert a staking event if it doesn't exist."""
    with conn.cursor() as cur:
        # Check if already exists
        cur.execute("""
            SELECT 1 FROM staking_events 
            WHERE tx_hash = %s AND event_type = %s
        """, (tx_hash, event_type))
        
        if cur.fetchone():
            return False  # Already exists
        
        cur.execute("""
            INSERT INTO staking_events (wallet_id, validator_id, event_type, amount, tx_hash, block_timestamp)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (wallet_id, validator_id, event_type, str(int(amount)), tx_hash, str(block_timestamp)))
        
        return True

def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    
    # Get user's wallets
    wallets = get_user_wallets(conn, user_id=3)  # Aaron's user_id
    print(f"Found {len(wallets)} wallets")
    
    # Get validators from staking positions
    validators = get_staking_positions(conn)
    print(f"Found {len(validators)} validators")
    
    total_inserted = 0
    
    for validator in validators:
        print(f"\nProcessing {validator}...")
        
        # Fetch stakes (deposit_and_stake)
        stakes = fetch_staking_txns(validator, 'deposit_and_stake')
        print(f"  Found {len(stakes)} stake transactions")
        
        for tx in stakes:
            signer = tx.get('predecessor_account_id')
            if signer not in wallets:
                continue  # Not user's transaction
            
            wallet_id = wallets[signer]
            amount = float(tx.get('actions_agg', {}).get('deposit', 0))
            tx_hash = tx.get('transaction_hash')
            block_timestamp = tx.get('block_timestamp')
            
            if amount > 0 and insert_staking_event(conn, wallet_id, validator, 'stake', amount, tx_hash, block_timestamp):
                ts = int(block_timestamp) / 1e9
                dt = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                print(f"  + {dt}: {signer} staked {amount/1e24:.2f} NEAR")
                total_inserted += 1
        
        # Fetch unstakes
        unstakes = fetch_staking_txns(validator, 'unstake')
        print(f"  Found {len(unstakes)} unstake transactions")
        
        for tx in unstakes:
            signer = tx.get('predecessor_account_id')
            if signer not in wallets:
                continue
            
            wallet_id = wallets[signer]
            # For unstake, amount is in the function args, not deposit
            # We'll need to parse args or estimate from pool balance changes
            # For now, skip unstakes - focus on stakes first
            pass
    
    print(f"\nTotal inserted: {total_inserted} staking events")
    conn.close()

if __name__ == '__main__':
    main()
