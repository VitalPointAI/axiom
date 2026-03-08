#!/usr/bin/env python3
"""
Quick staking sync for NearTax PostgreSQL.
Fetches current staking positions from FastNEAR and populates the DB.
"""

import os
import sys
import requests
import psycopg2
from datetime import datetime

# PostgreSQL connection
PG_CONN = "postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax"

FASTNEAR_API = "https://api.fastnear.com/v1"
NEARBLOCKS_API = "https://api.nearblocks.io/v1"
NEARBLOCKS_KEY = os.getenv("NEARBLOCKS_API_KEY", "0F1F69733B684BD48753570B3B9C4B27")


def get_db():
    return psycopg2.connect(PG_CONN)


def get_staking_pools(account_id: str) -> list:
    """Get list of pools an account stakes with via FastNEAR."""
    url = f"{FASTNEAR_API}/account/{account_id}/staking"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("pools", [])
    except Exception as e:
        print(f"  Error fetching staking for {account_id}: {e}")
    return []


def get_pool_balance(account_id: str, pool_id: str) -> int:
    """Get staked balance in a pool via NEAR RPC view call."""
    url = "https://rpc.mainnet.near.org"
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "query",
        "params": {
            "request_type": "call_function",
            "finality": "final",
            "account_id": pool_id,
            "method_name": "get_account",
            "args_base64": __import__('base64').b64encode(
                f'{{"account_id": "{account_id}"}}'.encode()
            ).decode()
        }
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        data = resp.json()
        if "result" in data and "result" in data["result"]:
            import json
            result_bytes = bytes(data["result"]["result"])
            result = json.loads(result_bytes.decode())
            staked = int(result.get("staked_balance", "0"))
            unstaked = int(result.get("unstaked_balance", "0"))
            return staked, unstaked
    except Exception as e:
        print(f"    RPC error for {pool_id}: {e}")
    return 0, 0


def get_stake_txns(account_id: str, per_page: int = 100) -> list:
    """Fetch staking transactions from NearBlocks."""
    url = f"{NEARBLOCKS_API}/account/{account_id}/stake-txns"
    headers = {"Authorization": f"Bearer {NEARBLOCKS_KEY}"} if NEARBLOCKS_KEY else {}
    all_txns = []
    page = 1
    
    while True:
        try:
            resp = requests.get(url, headers=headers, params={"page": page, "per_page": per_page}, timeout=30)
            if resp.status_code != 200:
                break
            data = resp.json()
            txns = data.get("txns", [])
            if not txns:
                break
            all_txns.extend(txns)
            if len(txns) < per_page:
                break
            page += 1
        except Exception as e:
            print(f"  Error fetching stake txns: {e}")
            break
    
    return all_txns


def sync_staking(user_id: int = None):
    """Main sync function."""
    conn = get_db()
    cur = conn.cursor()
    
    # Get all NEAR wallets
    if user_id:
        cur.execute("""
            SELECT id, account_id FROM wallets 
            WHERE chain = 'NEAR' AND user_id = %s
            AND account_id NOT LIKE '%%.pool%%'
            AND account_id NOT LIKE '%%.poolv1%%'
            AND account_id NOT LIKE '%%meta-pool%%'
            AND account_id NOT LIKE '%%linear-protocol%%'
        """, (user_id,))
    else:
        cur.execute("""
            SELECT id, account_id FROM wallets 
            WHERE chain = 'NEAR'
            AND account_id NOT LIKE '%%.pool%%'
            AND account_id NOT LIKE '%%.poolv1%%'
            AND account_id NOT LIKE '%%meta-pool%%'
            AND account_id NOT LIKE '%%linear-protocol%%'
        """)
    wallets = cur.fetchall()
    print(f"Found {len(wallets)} NEAR wallets to check")
    
    total_staked = 0
    positions_added = 0
    events_added = 0
    
    for wallet_id, account_id in wallets:
        print(f"\nProcessing: {account_id}")
        
        # Get staking pools
        pools = get_staking_pools(account_id)
        if not pools:
            print(f"  No staking pools found")
            continue
        
        print(f"  Found {len(pools)} pools")
        
        for pool_info in pools:
            pool_id = pool_info.get("pool_id", "")
            if not pool_id:
                continue
            
            # Get current balance via RPC
            staked, unstaked = get_pool_balance(account_id, pool_id)
            if staked == 0 and unstaked == 0:
                continue
            
            staked_near = staked / 1e24
            unstaked_near = unstaked / 1e24
            total_staked += staked_near
            
            print(f"    {pool_id}: {staked_near:.2f} staked, {unstaked_near:.2f} unstaked")
            
            # Upsert staking position
            try:
                cur.execute("""
                    INSERT INTO staking_positions 
                        (wallet_id, validator, staked_amount, unstaked_amount, updated_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (wallet_id, validator) 
                    DO UPDATE SET 
                        staked_amount = EXCLUDED.staked_amount,
                        unstaked_amount = EXCLUDED.unstaked_amount,
                        updated_at = NOW()
                """, (wallet_id, pool_id, str(staked), str(unstaked)))
                conn.commit()
                positions_added += 1
            except Exception as e:
                print(f"    Error upserting position: {e}")
                conn.rollback()
        
        # Fetch and store staking events (for history)
        txns = get_stake_txns(account_id)
        if txns:
            print(f"  Found {len(txns)} staking transactions")
            
            for tx in txns:
                tx_hash = tx.get("transaction_hash", "")
                block_height = tx.get("included_in_block_height", 0)
                block_ts = int(tx.get("block_timestamp", 0))
                receiver = tx.get("receiver_account_id", "")
                actions = tx.get("actions", [])
                deposit = int(tx.get("actions_agg", {}).get("deposit", 0))
                
                if not actions:
                    continue
                
                action = actions[0]
                method = action.get("method", "")
                args = action.get("args", {})
                
                # Determine event type
                event_type = None
                amount = 0
                validator = receiver if "pool" in receiver else ""
                
                if method in ("deposit_and_stake", "stake", "stake_all"):
                    event_type = "stake"
                    amount = deposit if deposit else int(args.get("amount", 0))
                elif method == "unstake":
                    event_type = "unstake"
                    amount = int(args.get("amount", 0))
                elif method == "unstake_all":
                    event_type = "unstake_all"
                    amount = 0  # Unknown, would need to look up
                elif method in ("withdraw", "withdraw_all"):
                    event_type = "withdraw"
                    amount = int(args.get("amount", 0)) if args.get("amount") else 0
                
                if not event_type or not validator:
                    continue
                
                # Insert event (skip duplicates)
                try:
                    cur.execute("""
                        INSERT INTO staking_events 
                            (wallet_id, validator_id, event_type, amount, tx_hash, block_timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (wallet_id, validator, event_type, str(amount), tx_hash, block_ts))
                    events_added += 1
                except Exception as e:
                    conn.rollback()  # Rollback and continue
        
        # Commit after each wallet
        try:
            conn.commit()
        except:
            conn.rollback()
    
    conn.commit()
    conn.close()
    
    print(f"\n{'='*50}")
    print(f"Sync complete!")
    print(f"  Total staked: {total_staked:.2f} NEAR")
    print(f"  Positions added/updated: {positions_added}")
    print(f"  Events added: {events_added}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', type=int, help='Sync only this user ID')
    args = parser.parse_args()
    sync_staking(args.user)
