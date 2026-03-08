#!/usr/bin/env python3
"""Check the two problem transactions"""
import requests
import os

ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
url = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()

# Check top OUT transactions
problem_txs = [
    '0x4d23a373cf170883dc1b0ad0c90c65789237b97d9375586bd4fdce003554ddcb',  # 4.00 ETH
    '0x8a158288660d03bf0c0b326377723e80f604671ee32707a4eeb4d1b72cd991f6',  # 1.95 ETH
    '0x80ab43569cd42dc25c0824f8718eb0a026108cc1514833eb28a2042eacb88be4',  # 1.92 ETH
]

for tx_hash in problem_txs:
    print(f"\n{'='*60}")
    print(f"TX: {tx_hash[:20]}...")
    print(f"{'='*60}")
    
    # Get transaction details
    response = requests.post(url, json={
        'jsonrpc': '2.0', 'id': 1,
        'method': 'eth_getTransactionByHash',
        'params': [tx_hash]
    })
    tx = response.json().get('result', {})
    
    if tx:
        print(f"From:  {tx.get('from')}")
        print(f"To:    {tx.get('to')}")
        val = int(tx.get('value', '0x0'), 16) / 1e18
        print(f"Value: {val:.6f} ETH")
        
        is_from_us = tx.get('from', '').lower() == address
        print(f"We sent this: {is_from_us}")
    else:
        print("Transaction not found!")
    
    # Get traces
    response = requests.post(url, json={
        'jsonrpc': '2.0', 'id': 1,
        'method': 'trace_transaction',
        'params': [tx_hash]
    })
    traces = response.json().get('result') or []
    print(f"\nTraces: {len(traces)}")
    
    for i, t in enumerate(traces[:10]):
        action = t.get('action', {})
        trace_from = action.get('from', '')[:16]
        trace_to = action.get('to', '')[:16]
        val = int(action.get('value', '0x0'), 16) / 1e18
        tt = t.get('type')
        
        is_our_out = action.get('from', '').lower() == address
        is_our_in = action.get('to', '').lower() == address
        
        marker = ''
        if is_our_out:
            marker = ' <-- OUR OUT'
        if is_our_in:
            marker = ' <-- OUR IN'
        
        if val > 0:
            print(f"  [{i}] {tt}: {trace_from}... -> {trace_to}... = {val:.6f} ETH{marker}")
