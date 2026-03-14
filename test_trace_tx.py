#!/usr/bin/env python3
"""Test trace_transaction to see if it's available on free tier"""
import requests
import os
import sqlite3

ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
url = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'

# Get a sample tx hash from our database
conn = sqlite3.connect('/home/deploy/neartax/neartax.db')
cursor = conn.cursor()
cursor.execute("""
    SELECT tx_hash FROM transactions
    WHERE wallet_id = 75 AND action_type = 'TRANSFER' AND direction = 'IN'
    LIMIT 5
""")
tx_hashes = [row[0] for row in cursor.fetchall()]
conn.close()

print(f"Testing trace_transaction on {len(tx_hashes)} transactions...")

for tx_hash in tx_hashes:
    print(f"\n{tx_hash[:20]}...")
    response = requests.post(url, json={
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'trace_transaction',
        'params': [tx_hash]
    })

    data = response.json()
    if 'error' in data:
        print(f"  Error: {data['error']}")
        break
    else:
        traces = data.get('result', [])
        print(f"  Got {len(traces)} traces")

        # Look for suicide (SELFDESTRUCT)
        for t in traces:
            if t.get('type') == 'suicide':
                val = int(t.get('action', {}).get('balance', '0x0'), 16) / 1e18
                print(f"  → SELFDESTRUCT: {val:.6f} ETH")
