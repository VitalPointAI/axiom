#!/usr/bin/env python3
import requests
import os

ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
url = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()

# Check outgoing traces
response = requests.post(url, json={
    'jsonrpc': '2.0',
    'id': 1,
    'method': 'trace_filter',
    'params': [{
        'fromAddress': [address],
        'fromBlock': 'earliest',
        'toBlock': 'latest'
    }]
}, timeout=60)

data = response.json()
if 'error' in data:
    print(f'Error: {data["error"]}')
else:
    traces = data.get('result', [])
    print(f'Outgoing traces: {len(traces)}')
    
    by_type = {}
    for t in traces:
        tt = t.get('type', 'unknown')
        val = int(t.get('action', {}).get('value', '0x0'), 16) / 1e18
        if tt not in by_type:
            by_type[tt] = {'count': 0, 'value': 0}
        by_type[tt]['count'] += 1
        by_type[tt]['value'] += val
    
    for t, d in by_type.items():
        print(f'  {t}: {d["count"]} traces, {d["value"]:.6f} ETH')
    
    # Show first few with value
    print("\nSample traces with value:")
    shown = 0
    for t in traces:
        val = int(t.get('action', {}).get('value', '0x0'), 16) / 1e18
        if val > 0 and shown < 5:
            print(f"  {t.get('type')}: {val:.6f} ETH to {t.get('action', {}).get('to', 'n/a')[:20]}")
            shown += 1
