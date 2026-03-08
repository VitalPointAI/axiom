#!/usr/bin/env python3
import requests
import os
import sys

ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
url = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'

print(f"Testing trace_filter for {address[:10]}...")
print(f"Using Alchemy URL: {url[:50]}...")

# Try trace_filter - toAddress (incoming)
response = requests.post(url, json={
    'jsonrpc': '2.0',
    'id': 1,
    'method': 'trace_filter',
    'params': [{
        'toAddress': [address.lower()],
        'fromBlock': 'earliest',
        'toBlock': 'latest',
        'count': 100
    }]
})

data = response.json()
if 'error' in data:
    print('Error:', data['error'])
    sys.exit(1)

traces_in = data.get('result', [])
print(f'Got {len(traces_in)} incoming traces')

# Check for SELFDESTRUCT (suicide type)
selfdestruct_count = 0
selfdestruct_value = 0
for t in traces_in:
    trace_type = t.get('type', '')
    if trace_type == 'suicide':
        selfdestruct_count += 1
        val = int(t.get('action', {}).get('balance', '0x0'), 16) / 1e18
        selfdestruct_value += val
        print(f"  SELFDESTRUCT: {val:.6f} ETH from {t.get('action', {}).get('address', 'unknown')[:16]}")

print(f"\nSELFDESTRUCT transfers: {selfdestruct_count} totaling {selfdestruct_value:.6f} ETH")

# Also check for any 'create' (constructor) transfers
create_count = 0
create_value = 0
for t in traces_in:
    if t.get('type') == 'create':
        create_count += 1
        val = int(t.get('action', {}).get('value', '0x0'), 16) / 1e18
        create_value += val

print(f"CREATE transfers: {create_count} totaling {create_value:.6f} ETH")

# Now also check fromAddress (outgoing)
response2 = requests.post(url, json={
    'jsonrpc': '2.0',
    'id': 2,
    'method': 'trace_filter',
    'params': [{
        'fromAddress': [address.lower()],
        'fromBlock': 'earliest',
        'toBlock': 'latest',
        'count': 100
    }]
})

data2 = response2.json()
if 'error' not in data2:
    traces_out = data2.get('result', [])
    print(f'\nGot {len(traces_out)} outgoing traces')
