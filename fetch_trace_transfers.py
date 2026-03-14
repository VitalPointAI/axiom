#!/usr/bin/env python3
"""Fetch trace transfers and add to database"""
import requests
import os
import sqlite3

ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
url = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()
wallet_id = 75

def get_block_timestamp(block_hex):
    """Get block timestamp"""
    response = requests.post(url, json={
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'eth_getBlockByNumber',
        'params': [block_hex, False]
    })
    data = response.json()
    if 'result' in data and data['result']:
        return int(data['result']['timestamp'], 16) * 1_000_000_000
    return None

print(f"Fetching trace transfers for {address[:16]}...")

# Fetch incoming traces
response = requests.post(url, json={
    'jsonrpc': '2.0',
    'id': 1,
    'method': 'trace_filter',
    'params': [{
        'toAddress': [address],
        'fromBlock': 'earliest',
        'toBlock': 'latest'
    }]
}, timeout=60)

data = response.json()
if 'error' in data:
    print(f"Error: {data['error']}")
    exit(1)

traces = data.get('result', [])
print(f"Got {len(traces)} incoming traces")

# Process traces
conn = sqlite3.connect('/home/deploy/neartax/neartax.db')
cursor = conn.cursor()

inserted = 0
for t in traces:
    trace_type = t.get('type', '')
    action = t.get('action', {})
    
    # Get value
    if trace_type == 'suicide':
        value = int(action.get('balance', '0x0'), 16) / 1e18
        from_addr = action.get('address', '')
    else:
        value = int(action.get('value', '0x0'), 16) / 1e18
        from_addr = action.get('from', '')
    
    if value == 0:
        continue
    
    tx_hash = t.get('transactionHash', '')
    block_raw = t.get('blockNumber')
    if isinstance(block_raw, int):
        block_num = block_raw
    elif isinstance(block_raw, str):
        block_num = int(block_raw, 16) if block_raw.startswith('0x') else int(block_raw)
    else:
        block_num = 0
    
    # Get timestamp
    block_ts = get_block_timestamp(hex(block_num)) if block_num else None
    
    # Create unique hash for trace (include trace position)
    trace_addr = t.get('traceAddress', [])
    trace_suffix = '_trace_' + '_'.join(map(str, trace_addr)) if trace_addr else '_trace_0'
    unique_hash = tx_hash + trace_suffix
    
    print(f"  {trace_type}: {value:.6f} ETH from {from_addr[:16]}... (block {block_num})")
    
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO transactions 
            (wallet_id, tx_hash, block_height, block_timestamp, action_type, 
             direction, counterparty, amount, asset, success, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            wallet_id,
            unique_hash,
            block_num,
            block_ts,
            'TRACE_' + trace_type.upper(),
            'IN',
            from_addr,
            value,
            'ETH',
            1,
            'alchemy_trace'
        ))
        
        if cursor.rowcount > 0:
            inserted += 1
    except Exception as e:
        print(f"    Error: {e}")

conn.commit()
conn.close()

print(f"\nInserted {inserted} trace transfers")
