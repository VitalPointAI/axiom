#!/usr/bin/env python3
"""
Backfill missing prices in defi_events table.
Uses Ref Finance API for current prices and applies them to historical events.
"""

import psycopg2
import requests

PG_CONN = 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'

# Stablecoins always $1
STABLECOINS = ['USDC', 'USDC.e', 'USDT', 'USDT.e', 'DAI', 'USN']

# Token contract mappings for Ref Finance
TOKEN_CONTRACTS = {
    'wNEAR': 'wrap.near',
    'STNEAR': 'meta-pool.near',
    'BRRR': 'token.burrow.near',
    'ETH': '...',  # Will get from Ref
    'ZEC': 'zec.omft.near',
    'AURORA': 'aaaaaa20d9e0e2461697782ef11675f668207961.factory.bridge.near',
    'mpDAO': 'mpdao-token.near',
    '$META': 'meta-token.near',
    'rNEAR': 'lst.rhealab.near',
    'LONK': 'lonk.tkn.near',
    'NEKO': 'ftv2.nekotoken.near',
    'SWEAT': 'token.sweat',
    'PARAS': 'token.paras.near',
}


def get_ref_prices():
    """Fetch all token prices from Ref Finance."""
    try:
        resp = requests.get('https://api.ref.finance/list-token-price', timeout=10)
        if resp.ok:
            data = resp.json()
            prices = {}
            for contract_id, info in data.items():
                price = float(info.get('price', 0))
                symbol = info.get('symbol', '')
                if price > 0:
                    prices[contract_id] = price
                    if symbol:
                        prices[symbol] = price
                        prices[symbol.upper()] = price
            return prices
    except Exception as e:
        print(f"Error fetching Ref prices: {e}")
    return {}


def backfill_prices():
    """Backfill missing prices in defi_events."""
    conn = psycopg2.connect(PG_CONN)
    cur = conn.cursor()
    
    # Get Ref Finance prices
    print("Fetching Ref Finance prices...")
    ref_prices = get_ref_prices()
    print(f"Got {len(ref_prices)} prices from Ref Finance")
    
    # Get NEAR price for wNEAR/stNEAR
    near_price = ref_prices.get('wrap.near', 0)
    print(f"NEAR price: ${near_price:.4f}")
    
    # stNEAR trades at slight premium to NEAR
    stnear_price = ref_prices.get('meta-pool.near', near_price * 1.02)
    print(f"stNEAR price: ${stnear_price:.4f}")
    
    # BRRR price
    brrr_price = ref_prices.get('token.burrow.near', 0)
    print(f"BRRR price: ${brrr_price:.6f}")
    
    updated_count = 0
    
    # 1. Stablecoins = $1
    print("\nUpdating stablecoins...")
    for stable in STABLECOINS:
        cur.execute("""
            UPDATE defi_events 
            SET price_usd = 1.0, 
                value_usd = amount_decimal * 1.0
            WHERE token_symbol = %s 
              AND (value_usd IS NULL OR value_usd = 0)
              AND amount_decimal IS NOT NULL
        """, (stable,))
        if cur.rowcount > 0:
            print(f"  {stable}: {cur.rowcount} updated")
            updated_count += cur.rowcount
    
    # 2. wNEAR = NEAR price
    if near_price > 0:
        print(f"\nUpdating wNEAR at ${near_price:.4f}...")
        cur.execute("""
            UPDATE defi_events 
            SET price_usd = %s, 
                value_usd = amount_decimal * %s
            WHERE token_symbol = 'wNEAR' 
              AND (value_usd IS NULL OR value_usd = 0)
              AND amount_decimal IS NOT NULL
        """, (near_price, near_price))
        print(f"  wNEAR: {cur.rowcount} updated")
        updated_count += cur.rowcount
    
    # 3. stNEAR
    if stnear_price > 0:
        print(f"\nUpdating stNEAR at ${stnear_price:.4f}...")
        cur.execute("""
            UPDATE defi_events 
            SET price_usd = %s, 
                value_usd = amount_decimal * %s
            WHERE token_symbol = 'STNEAR' 
              AND (value_usd IS NULL OR value_usd = 0)
              AND amount_decimal IS NOT NULL
        """, (stnear_price, stnear_price))
        print(f"  stNEAR: {cur.rowcount} updated")
        updated_count += cur.rowcount
    
    # 4. BRRR
    if brrr_price > 0:
        print(f"\nUpdating BRRR at ${brrr_price:.6f}...")
        cur.execute("""
            UPDATE defi_events 
            SET price_usd = %s, 
                value_usd = amount_decimal * %s
            WHERE token_symbol = 'BRRR' 
              AND (value_usd IS NULL OR value_usd = 0)
              AND amount_decimal IS NOT NULL
        """, (brrr_price, brrr_price))
        print(f"  BRRR: {cur.rowcount} updated")
        updated_count += cur.rowcount
    
    # 5. Other tokens from Ref
    print("\nUpdating other tokens from Ref Finance...")
    for symbol, contract in TOKEN_CONTRACTS.items():
        if symbol in STABLECOINS or symbol in ['wNEAR', 'STNEAR', 'BRRR']:
            continue
        price = ref_prices.get(contract) or ref_prices.get(symbol) or ref_prices.get(symbol.upper())
        if price and price > 0:
            cur.execute("""
                UPDATE defi_events 
                SET price_usd = %s, 
                    value_usd = amount_decimal * %s
                WHERE token_symbol = %s 
                  AND (value_usd IS NULL OR value_usd = 0)
                  AND amount_decimal IS NOT NULL
            """, (price, price, symbol))
            if cur.rowcount > 0:
                print(f"  {symbol}: {cur.rowcount} updated at ${price:.6f}")
                updated_count += cur.rowcount
    
    conn.commit()
    
    # Check remaining missing
    cur.execute("SELECT COUNT(*) FROM defi_events WHERE value_usd IS NULL OR value_usd = 0")
    remaining = cur.fetchone()[0]
    
    print(f"\n✅ Updated {updated_count} events")
    print(f"📊 Still missing prices: {remaining}")
    
    if remaining > 0:
        cur.execute("""
            SELECT token_symbol, COUNT(*) as missing 
            FROM defi_events 
            WHERE value_usd IS NULL OR value_usd = 0 
            GROUP BY token_symbol 
            ORDER BY missing DESC 
            LIMIT 10
        """)
        print("\nRemaining tokens without prices:")
        for row in cur.fetchall():
            print(f"  {row[0]}: {row[1]}")
    
    cur.close()
    conn.close()


if __name__ == '__main__':
    backfill_prices()
