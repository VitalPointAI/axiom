#!/usr/bin/env python3
"""
Backfill historical prices for transactions and calculate cost basis.

Uses CryptoCompare API for historical hourly prices.
Bank of Canada for CAD exchange rates.
"""

import sqlite3
import requests
from datetime import datetime, timezone
import time
from typing import Optional, Dict
import sys

# CryptoCompare API (free tier: 100,000 calls/month)
CC_API_URL = "https://min-api.cryptocompare.com/data/v2/histohour"

# Bank of Canada daily exchange rates
BOC_API_URL = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json"

# Token contract -> CryptoCompare symbol mapping
TOKEN_MAP = {
    'near': 'NEAR',
    'wrap.near': 'NEAR',  # wNEAR is pegged to NEAR
    'token.v2.ref-finance.near': 'REF',
    'meta-pool.near': 'NEAR',  # stNEAR is ~NEAR
    'meta-token.near': 'NEAR',  # META tracks NEAR
    'token.burrow.near': 'NEAR',  # BRRR approximation
    'usdt.tether-token.near': 'USDT',
    'dac17f958d2ee523a2206206994597c13d831ec7.factory.bridge.near': 'USDT',
    'a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.factory.bridge.near': 'USDC',
    '17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1': 'USDC',  # USDC on NEAR
    'aurora': 'AURORA',
    'eth': 'ETH',
    'btc': 'BTC',
}

# Cache for prices to avoid repeated API calls
price_cache: Dict[str, float] = {}
cad_rate_cache: Dict[str, float] = {}


def get_usd_price(symbol: str, timestamp_ns: int) -> Optional[float]:
    """Get USD price for a token at a specific timestamp."""
    # Convert nanoseconds to seconds
    ts_sec = timestamp_ns // 1_000_000_000
    
    # Round to hour for caching
    hour_ts = (ts_sec // 3600) * 3600
    cache_key = f"{symbol}:{hour_ts}"
    
    if cache_key in price_cache:
        return price_cache[cache_key]
    
    # Skip if symbol not in supported list
    if symbol not in ['NEAR', 'BTC', 'ETH', 'USDT', 'USDC', 'AURORA', 'REF']:
        return None
    
    try:
        params = {
            'fsym': symbol,
            'tsym': 'USD',
            'limit': 1,
            'toTs': hour_ts
        }
        resp = requests.get(CC_API_URL, params=params, timeout=10)
        data = resp.json()
        
        if data.get('Response') == 'Success' and data.get('Data', {}).get('Data'):
            price_data = data['Data']['Data']
            if price_data:
                price = price_data[-1].get('close', 0)
                price_cache[cache_key] = price
                return price
    except Exception as e:
        print(f"Error fetching price for {symbol}: {e}")
    
    return None


def get_cad_rate(date_str: str) -> float:
    """Get USD to CAD exchange rate for a date."""
    if date_str in cad_rate_cache:
        return cad_rate_cache[date_str]
    
    try:
        params = {
            'start_date': date_str,
            'end_date': date_str
        }
        resp = requests.get(BOC_API_URL, params=params, timeout=10)
        data = resp.json()
        
        observations = data.get('observations', [])
        if observations:
            rate = float(observations[0].get('FXUSDCAD', {}).get('v', 1.35))
            cad_rate_cache[date_str] = rate
            return rate
    except Exception as e:
        print(f"Error fetching CAD rate for {date_str}: {e}")
    
    return 1.35  # Default fallback


def backfill_transaction_prices(db_path: str = 'neartax.db', limit: int = 1000):
    """Backfill prices for transactions missing cost basis."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get transactions missing prices (with significant amounts)
    cur.execute('''
        SELECT id, tx_hash, block_timestamp, amount, direction, tax_category
        FROM transactions
        WHERE cost_basis_usd IS NULL
        AND CAST(amount AS REAL) / 1e24 > 0.1
        AND block_timestamp IS NOT NULL
        ORDER BY block_timestamp DESC
        LIMIT ?
    ''', (limit,))
    
    transactions = cur.fetchall()
    print(f"Found {len(transactions)} transactions to price")
    
    updated = 0
    for i, tx in enumerate(transactions):
        if i % 100 == 0:
            print(f"Processing {i}/{len(transactions)}...")
            time.sleep(0.5)  # Rate limit
        
        amount_near = float(tx['amount']) / 1e24
        timestamp = tx['block_timestamp']
        
        # Get NEAR price
        price_usd = get_usd_price('NEAR', timestamp)
        if price_usd is None:
            continue
        
        value_usd = amount_near * price_usd
        
        # Get CAD rate
        dt = datetime.fromtimestamp(timestamp / 1_000_000_000, tz=timezone.utc)
        date_str = dt.strftime('%Y-%m-%d')
        cad_rate = get_cad_rate(date_str)
        value_cad = value_usd * cad_rate
        
        # Update transaction
        cur.execute('''
            UPDATE transactions
            SET cost_basis_usd = ?,
                cost_basis_cad = ?,
                price_warning = NULL,
                price_resolved = 1
            WHERE id = ?
        ''', (value_usd, value_cad, tx['id']))
        
        updated += 1
        
        # Batch commit
        if updated % 50 == 0:
            conn.commit()
    
    conn.commit()
    print(f"Updated {updated} transactions with prices")
    
    # Now do FT transactions
    cur.execute('''
        SELECT id, tx_hash, block_timestamp, token_symbol, token_contract, 
               amount, token_decimals
        FROM ft_transactions
        WHERE value_usd IS NULL
        AND CAST(amount AS REAL) > 0
        AND block_timestamp IS NOT NULL
        ORDER BY block_timestamp DESC
        LIMIT ?
    ''', (limit,))
    
    ft_transactions = cur.fetchall()
    print(f"Found {len(ft_transactions)} FT transactions to price")
    
    ft_updated = 0
    for i, tx in enumerate(ft_transactions):
        if i % 100 == 0:
            print(f"Processing FT {i}/{len(ft_transactions)}...")
            time.sleep(0.5)
        
        decimals = tx['token_decimals'] or 18
        amount = float(tx['amount']) / (10 ** decimals)
        timestamp = tx['block_timestamp']
        
        # Map token to symbol
        contract = tx['token_contract'] or ''
        symbol = TOKEN_MAP.get(contract.lower(), tx['token_symbol'])
        
        if not symbol or symbol in ['BRRR', '$META', 'CAT', 'BLACKDRAGON', 'BABYBLACKDRAGON']:
            # Skip tokens without reliable price feeds or spam
            continue
        
        price_usd = get_usd_price(symbol, timestamp)
        if price_usd is None:
            continue
        
        value_usd = amount * price_usd
        
        # Get CAD rate
        dt = datetime.fromtimestamp(timestamp / 1_000_000_000, tz=timezone.utc)
        date_str = dt.strftime('%Y-%m-%d')
        cad_rate = get_cad_rate(date_str)
        value_cad = value_usd * cad_rate
        
        # Update
        cur.execute('''
            UPDATE ft_transactions
            SET price_usd = ?,
                value_usd = ?,
                value_cad = ?
            WHERE id = ?
        ''', (price_usd, value_usd, value_cad, tx['id']))
        
        ft_updated += 1
        
        if ft_updated % 50 == 0:
            conn.commit()
    
    conn.commit()
    print(f"Updated {ft_updated} FT transactions with prices")
    
    conn.close()
    
    return {
        'transactions_updated': updated,
        'ft_updated': ft_updated,
        'price_cache_size': len(price_cache),
        'cad_cache_size': len(cad_rate_cache)
    }


if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'neartax.db'
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    
    print(f"Backfilling prices for up to {limit} transactions...")
    result = backfill_transaction_prices(db_path, limit)
    
    print("\nResults:")
    print(f"  Transactions updated: {result['transactions_updated']}")
    print(f"  FT transactions updated: {result['ft_updated']}")
    print(f"  Price cache entries: {result['price_cache_size']}")
    print(f"  CAD rate cache entries: {result['cad_cache_size']}")
