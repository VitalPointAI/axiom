#!/usr/bin/env python3
"""
Fast balance snapshot - native tokens only.
For FT tokens, we'll use NearBlocks API (with rate limiting).
"""

import os
import sys
import argparse
import random
import requests
import time
import json
import logging
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)

DB_URL = os.environ.get('DATABASE_URL', 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax')
NEAR_RPC = os.environ.get("NEAR_RPC_URL", "https://rpc.fastnear.com")

def get_connection():
    return psycopg2.connect(DB_URL)

def fetch_near_balance(account_id: str) -> float:
    """Fetch native NEAR balance from RPC."""
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "dontcare",
            "method": "query",
            "params": {
                "request_type": "view_account",
                "finality": "final",
                "account_id": account_id
            }
        }
        resp = requests.post(NEAR_RPC, json=payload, timeout=10)
        data = resp.json()
        if 'error' in data:
            return 0.0
        amount = data.get('result', {}).get('amount', '0')
        return int(amount) / 1e24
    except (requests.RequestException, ConnectionError, TimeoutError, ValueError, KeyError) as e:
        logger.warning("Failed to fetch NEAR balance for %s: %s", account_id, e)
        return 0.0

def fetch_ft_balances_nearblocks(account_id: str, max_retries: int = 5) -> list:
    """Fetch FT balances from NearBlocks with exponential backoff + jitter.

    Retry strategy (2^attempt + uniform jitter in [0, 1)) for 429, Timeout,
    and ConnectionError — no silent data loss.
    """
    nearblocks_base = os.environ.get("NEARBLOCKS_API_URL", "https://api.nearblocks.io/v1")
    url = f"{nearblocks_base}/account/{account_id}/ft"

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=15)

            if resp.status_code == 429:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "NearBlocks 429 rate limited fetching FT balances for %s, "
                    "retry %d/%d in %.1fs",
                    account_id, attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
                continue

            if resp.status_code != 200:
                logger.warning(
                    "NearBlocks FT balance returned %d for %s",
                    resp.status_code, account_id,
                )
                return []

            data = resp.json()
            tokens = data.get("inventory", {}).get("fts", [])

            result = []
            for t in tokens:
                contract = t.get("contract", "")
                if contract == "aurora":
                    continue
                symbol = t.get("ft_meta", {}).get("symbol", "UNKNOWN")
                decimals = t.get("ft_meta", {}).get("decimals", 18)
                amount = t.get("amount", "0")

                try:
                    balance = float(amount) / (10 ** int(decimals))
                except (ValueError, TypeError, ZeroDivisionError) as e:
                    logger.warning(
                        "Failed to parse FT balance for contract %s: %s", contract, e
                    )
                    balance = 0.0

                if balance > 0.0001:
                    result.append({
                        "contract": contract,
                        "symbol": symbol.upper(),
                        "balance": balance,
                    })

            return result

        except requests.exceptions.Timeout:
            wait = (2 ** attempt) + random.uniform(0, 1)
            logger.warning(
                "NearBlocks timeout fetching FT balances for %s, retry %d/%d in %.1fs",
                account_id, attempt + 1, max_retries, wait,
            )
            time.sleep(wait)

        except requests.exceptions.ConnectionError:
            wait = (2 ** attempt) + random.uniform(0, 1)
            logger.warning(
                "NearBlocks connection error fetching FT balances for %s, retry %d/%d in %.1fs",
                account_id, attempt + 1, max_retries, wait,
            )
            time.sleep(wait)

        except (requests.RequestException, ValueError) as e:
            logger.warning(
                "Error fetching FT balances for %s (attempt %d/%d): %s",
                account_id, attempt + 1, max_retries, e,
            )
            if attempt < max_retries - 1:
                time.sleep((2 ** attempt) + random.uniform(0, 1))

    logger.error(
        "NearBlocks FT balance fetch failed after %d retries for %s",
        max_retries, account_id,
    )
    return []

def get_price(symbol: str, conn) -> float:
    """Get most recent price."""
    cur = conn.cursor()
    cur.execute("""
        SELECT price FROM price_cache 
        WHERE UPPER(coin_id) = UPPER(%s) AND currency = 'USD'
        ORDER BY date DESC LIMIT 1
    """, (symbol,))
    row = cur.fetchone()
    cur.close()
    return float(row[0]) if row else 0.0

def run_snapshot(snapshot_date: str = None, skip_ft: bool = False):
    """Run balance snapshot."""
    if snapshot_date is None:
        snapshot_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"=" * 60)
    print(f"Balance Snapshot: {snapshot_date}")
    print(f"=" * 60)
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Get NEAR wallets
    cur.execute("SELECT id, account_id FROM wallets WHERE chain = 'NEAR'")
    wallets = cur.fetchall()
    
    print(f"\nSnapshotting {len(wallets)} NEAR wallets...")
    
    snapshots = []
    near_price = get_price('NEAR', conn)
    
    for wallet_id, account_id in wallets:
        print(f"  {account_id}...", end=" ", flush=True)
        
        # Native NEAR
        near_balance = fetch_near_balance(account_id)
        if near_balance > 0.0001:
            snapshots.append((
                wallet_id, snapshot_date, 'NEAR', None, 
                near_balance, near_balance * near_price, near_price, 'NEAR'
            ))
            print(f"{near_balance:.4f} NEAR", end="", flush=True)
        
        # FT tokens (with rate limiting)
        if not skip_ft:
            ft_balances = fetch_ft_balances_nearblocks(account_id)
            for ft in ft_balances:
                price = get_price(ft['symbol'], conn)
                snapshots.append((
                    wallet_id, snapshot_date, ft['symbol'], ft['contract'],
                    ft['balance'], ft['balance'] * price, price, 'NEAR'
                ))
            if ft_balances:
                print(f" + {len(ft_balances)} tokens", end="", flush=True)
            time.sleep(2)  # Rate limit: ~30 calls/min
        
        print(flush=True)
    
    # EVM wallets (calculated from transactions)
    cur.execute("SELECT id, address, chain FROM evm_wallets WHERE is_owned = true")
    evm_wallets = cur.fetchall()
    
    if evm_wallets:
        print(f"\nSnapshotting {len(evm_wallets)} EVM wallets...")
        
        for wallet_id, address, chain in evm_wallets:
            native_symbol = {'ethereum': 'ETH', 'ETH': 'ETH', 'polygon': 'MATIC', 
                           'Polygon': 'MATIC', 'cronos': 'CRO', 'Cronos': 'CRO'}.get(chain, 'ETH')
            price = get_price(native_symbol, conn)
            
            cur.execute("""
                SELECT SUM(CASE 
                    WHEN LOWER(from_address) = LOWER(%s) THEN -CAST(value AS NUMERIC) / 1e18
                    WHEN LOWER(to_address) = LOWER(%s) THEN CAST(value AS NUMERIC) / 1e18
                    ELSE 0 END) as balance
                FROM evm_transactions 
                WHERE wallet_id = %s AND tx_type IN ('transfer', 'internal')
            """, (address, address, wallet_id))
            row = cur.fetchone()
            balance = float(row[0]) if row and row[0] else 0.0
            
            if balance > 0.0001:
                snapshots.append((
                    wallet_id, snapshot_date, native_symbol, None,
                    balance, balance * price, price, chain
                ))
                print(f"  {address[:10]}...{address[-6:]}: {balance:.4f} {native_symbol}")
    
    # XRP wallets
    cur.execute("""
        SELECT w.id, w.address, 
            COALESCE(SUM(CASE WHEN t.is_outgoing THEN -t.amount ELSE t.amount END), 0) as balance
        FROM xrp_wallets w
        LEFT JOIN xrp_transactions t ON w.id = t.wallet_id
        GROUP BY w.id, w.address
        HAVING COALESCE(SUM(CASE WHEN t.is_outgoing THEN -t.amount ELSE t.amount END), 0) > 0.0001
    """)
    xrp_wallets = cur.fetchall()
    
    if xrp_wallets:
        print(f"\nSnapshotting {len(xrp_wallets)} XRP wallets...")
        xrp_price = get_price('XRP', conn)
        
        for wallet_id, address, balance in xrp_wallets:
            balance = float(balance)
            snapshots.append((
                wallet_id, snapshot_date, 'XRP', None,
                balance, balance * xrp_price, xrp_price, 'xrp'
            ))
            print(f"  {address[:10]}...{address[-6:]}: {balance:.4f} XRP")
    
    # Save all snapshots
    if snapshots:
        execute_values(cur, """
            INSERT INTO balance_snapshots 
                (wallet_id, snapshot_date, token_symbol, token_contract, balance, balance_usd, price_usd, chain)
            VALUES %s
            ON CONFLICT (wallet_id, snapshot_date, token_symbol, token_contract) 
            DO UPDATE SET balance = EXCLUDED.balance, balance_usd = EXCLUDED.balance_usd, price_usd = EXCLUDED.price_usd
        """, snapshots)
        conn.commit()
    
    cur.close()
    conn.close()
    
    print(f"\n✅ Snapshot complete: {len(snapshots)} balance records saved")
    return len(snapshots)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', help='Snapshot date (YYYY-MM-DD)', default=None)
    parser.add_argument('--skip-ft', action='store_true', help='Skip FT token balances')
    args = parser.parse_args()
    run_snapshot(args.date, args.skip_ft)

if __name__ == '__main__':
    main()
