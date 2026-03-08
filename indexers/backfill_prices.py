#!/usr/bin/env python3
"""Backfill missing NEAR prices for epoch rewards."""

import requests
import psycopg2
import time
from datetime import datetime

CRYPTOCOMPARE_API = 'https://min-api.cryptocompare.com/data'
PG_CONN = 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'

conn = psycopg2.connect(PG_CONN)
cur = conn.cursor()

# Get missing dates
cur.execute('''
    SELECT DISTINCT epoch_date 
    FROM staking_epoch_rewards 
    WHERE near_price_usd IS NULL
    ORDER BY epoch_date
''')
missing_dates = [row[0].strftime('%Y-%m-%d') for row in cur.fetchall()]
print(f'Missing prices for {len(missing_dates)} dates')

for date_str in missing_dates:
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    ts = int(dt.timestamp())
    
    try:
        resp = requests.get(f'{CRYPTOCOMPARE_API}/pricehistorical', params={
            'fsym': 'NEAR',
            'tsyms': 'USD',
            'ts': ts
        }, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            price = data.get('NEAR', {}).get('USD')
            if price:
                # Update the records
                cur.execute('''
                    INSERT INTO price_cache (coin_id, date, currency, price)
                    VALUES ('near', %s, 'usd', %s)
                    ON CONFLICT (coin_id, date, currency) DO UPDATE SET price = EXCLUDED.price
                ''', (date_str, price))
                
                # Update rewards table
                cur.execute('''
                    UPDATE staking_epoch_rewards 
                    SET near_price_usd = %s,
                        near_price_cad = %s * 1.36,
                        reward_usd = reward_near * %s,
                        reward_cad = reward_near * %s * 1.36
                    WHERE epoch_date = %s AND near_price_usd IS NULL
                ''', (price, price, price, price, date_str))
                conn.commit()
                print(f'  {date_str}: ${price:.2f}')
        time.sleep(0.3)
    except Exception as e:
        print(f'  {date_str}: ERROR {e}')

conn.close()
print('Done!')
