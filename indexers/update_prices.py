#!/usr/bin/env python3
"""Daily price updater using CryptoCompare API."""

import requests
import psycopg2
import time
from datetime import datetime

PG_CONN = 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'
CRYPTOCOMPARE_URL = 'https://min-api.cryptocompare.com/data/v2/histoday'

# Primary tokens - fetch these first
PRIMARY_TOKENS = ['NEAR', 'ETH', 'BTC']
# Secondary tokens - add delay to avoid rate limits
SECONDARY_TOKENS = ['AKT', 'CRO', 'XRP', 'MATIC']

def update_prices():
    conn = psycopg2.connect(PG_CONN)
    cur = conn.cursor()

    all_tokens = PRIMARY_TOKENS + SECONDARY_TOKENS

    for i, token in enumerate(all_tokens):
        # Rate limit: wait between requests
        if i > 0:
            time.sleep(2)

        try:
            resp = requests.get(CRYPTOCOMPARE_URL, params={
                'fsym': token,
                'tsym': 'USD',
                'limit': 7
            }, timeout=30)
            data = resp.json()

            if data.get('Response') != 'Success':
                print(f'Skip {token}: {data.get("Message", "unknown error")[:50]}')
                continue

            prices = data.get('Data', {}).get('Data', [])
            for p in prices:
                dt = datetime.fromtimestamp(p['time'])
                date_str = dt.strftime('%Y-%m-%d 12:00')
                price = p['close']

                cur.execute('''
                    INSERT INTO price_cache (coin_id, date, currency, price, fetched_at)
                    VALUES (%s, %s, 'USD', %s, NOW())
                    ON CONFLICT (coin_id, date, currency)
                    DO UPDATE SET price = EXCLUDED.price, fetched_at = NOW()
                ''', (token, date_str, price))

            conn.commit()
            print(f'{token}: {len(prices)} prices')

        except Exception as e:
            print(f'Error {token}: {e}')
            conn.rollback()

    conn.close()
    print('Done!')

if __name__ == '__main__':
    update_prices()
