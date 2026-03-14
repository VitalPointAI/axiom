#!/usr/bin/env python3
"""Check DEX swaps for ETH that might be returning"""
import requests
import os
import sqlite3

ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
url = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()

# Known DEX routers
dex_routers = [
    '0x111111125434b319222',  # 1inch v4
    '0x11111254369792b2ca',   # 1inch v3
    '0x7a250d5630b4cf539',    # Uniswap v2 router
    '0xe592427a0aece92de',    # Uniswap v3 router
]

print("Analyzing 1inch transactions for ETH refunds...")

conn = sqlite3.connect('/home/deploy/neartax/neartax.db')
cursor = conn.cursor()

# Get 1inch OUT transactions
cursor.execute('''
    SELECT tx_hash, amount, counterparty
    FROM transactions
    WHERE wallet_id = 75
    AND direction = 'OUT'
    AND asset = 'ETH'
    AND LOWER(counterparty) LIKE '0x1111112%'
''')
oneinch_txs = cursor.fetchall()
print(f"Found {len(oneinch_txs)} 1inch OUT transactions")

total_out = sum(float(r[1]) for r in oneinch_txs)
print(f"Total ETH sent to 1inch: {total_out:.6f} ETH")

# For each 1inch tx, check if we have an internal transfer back
eth_returned = 0
for tx_hash, amount, _ in oneinch_txs[:10]:  # Check first 10
    # Use trace_transaction to see all transfers in this tx
    response = requests.post(url, json={
        'jsonrpc': '2.0', 'id': 1,
        'method': 'trace_transaction',
        'params': [tx_hash]
    }, timeout=30)

    traces = response.json().get('result', [])

    # Find any traces that send ETH back to our address
    for t in traces:
        action = t.get('action', {})
        if action.get('to', '').lower() == address:
            val = int(action.get('value', '0x0'), 16) / 1e18
            if val > 0:
                print(f"  TX {tx_hash[:16]}: sent {amount} ETH, got back {val:.6f} ETH")
                eth_returned += val

print(f"\nTotal ETH returned in sampled 1inch txs: {eth_returned:.6f} ETH")

# Now let's check ALL transactions for refunds using trace_filter
print("\n" + "="*50)
print("Checking ALL internal transfers TO this address...")

response = requests.post(url, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'trace_filter',
    'params': [{
        'toAddress': [address],
        'fromBlock': 'earliest',
        'toBlock': 'latest'
    }]
}, timeout=120)

traces_in = response.json().get('result', [])
print(f"Total incoming traces: {len(traces_in)}")

# Categorize by the parent transaction
by_tx = {}
for t in traces_in:
    tx_hash = t.get('transactionHash')
    val = int(t.get('action', {}).get('value', '0x0'), 16) / 1e18
    if tx_hash not in by_tx:
        by_tx[tx_hash] = 0
    by_tx[tx_hash] += val

# Check which of these we're missing
print("\nComparing with indexed data...")
cursor.execute('SELECT tx_hash FROM transactions WHERE wallet_id = 75 AND direction = \'IN\'')
indexed_in = set(r[0] for r in cursor.fetchall())

missing_value = 0
for tx_hash, val in by_tx.items():
    # Check if this tx_hash OR any variant is indexed
    found = tx_hash in indexed_in or (tx_hash + '_trace_0') in indexed_in
    if not found and val > 0:
        print(f"  MISSING: {tx_hash[:20]}... = {val:.6f} ETH")
        missing_value += val

print(f"\nTotal missing incoming value: {missing_value:.6f} ETH")

conn.close()
