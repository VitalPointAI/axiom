#!/usr/bin/env python3
"""Deep check for all possible ETH inflows"""
import requests
import os

ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
ETHERSCAN_KEY = os.environ.get('ETHERSCAN_API_KEY', '')
url = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()

print("="*60)
print("DEEP CHECK FOR MISSING ETH")
print("="*60)

# 1. Check Alchemy getAssetTransfers with ALL categories
print("\n1. Alchemy getAssetTransfers (all categories):")
categories = ['external', 'internal', 'erc20', 'erc721', 'erc1155', 'specialnft']

all_in = []
page_key = None
while True:
    params = {
        'toAddress': address,
        'category': categories,
        'withMetadata': True,
        'excludeZeroValue': False,
        'maxCount': '0x3e8'
    }
    if page_key:
        params['pageKey'] = page_key

    response = requests.post(url, json={
        'jsonrpc': '2.0', 'id': 1,
        'method': 'alchemy_getAssetTransfers',
        'params': [params]
    })

    result = response.json().get('result', {})
    transfers = result.get('transfers', [])
    all_in.extend(transfers)

    page_key = result.get('pageKey')
    if not page_key:
        break

eth_in = sum(t.get('value') or 0 for t in all_in if t.get('asset') == 'ETH')
print(f"   ETH incoming: {eth_in:.6f} ETH ({len([t for t in all_in if t.get('asset') == 'ETH'])} transfers)")

# 2. Check for any weird categories we might have missed
by_cat = {}
for t in all_in:
    cat = t.get('category', 'unknown')
    asset = t.get('asset', 'unknown')
    val = t.get('value') or 0
    if asset == 'ETH' and val > 0:
        if cat not in by_cat:
            by_cat[cat] = 0
        by_cat[cat] += val

print("   By category:", by_cat)

# 3. Check trace_filter with reward type
print("\n2. Trace filter (looking for reward/suicide):")
response = requests.post(url, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'trace_filter',
    'params': [{
        'toAddress': [address],
        'fromBlock': 'earliest',
        'toBlock': 'latest'
    }]
}, timeout=120)

traces = response.json().get('result', [])
trace_types = {}
for t in traces:
    tt = t.get('type', 'unknown')
    if tt == 'suicide':
        val = int(t.get('action', {}).get('balance', '0x0'), 16) / 1e18
    else:
        val = int(t.get('action', {}).get('value', '0x0'), 16) / 1e18
    if tt not in trace_types:
        trace_types[tt] = 0
    trace_types[tt] += val

print(f"   Trace types: {trace_types}")

# 4. Get on-chain balance
print("\n3. On-chain balance check:")
response = requests.post(url, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'eth_getBalance',
    'params': [address, 'latest']
})
on_chain = int(response.json().get('result', '0x0'), 16) / 1e18
print(f"   Current balance: {on_chain:.6f} ETH")

# 5. Get first transaction to see initial funding
print("\n4. First block activity:")
response = requests.post(url, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'alchemy_getAssetTransfers',
    'params': [{
        'toAddress': address,
        'category': ['external', 'internal'],
        'fromBlock': '0x0',
        'toBlock': '0x860000',  # First ~500k blocks
        'maxCount': '0x10'
    }]
})
early = response.json().get('result', {}).get('transfers', [])
print(f"   Early transfers (block < 8.6M): {len(early)}")
for t in early[:5]:
    val = t.get('value') or 0
    block = int(t.get('blockNum', '0x0'), 16)
    print(f"      Block {block}: {val:.6f} ETH from {t.get('from', '')[:16]}")

# 6. Calculate the gap
print("\n" + "="*60)
print("SUMMARY:")
known_in = 22.262118  # From our indexed data
known_out = 24.306743
computed = known_in - known_out
gap = on_chain - computed

print(f"   Known IN:  {known_in:.6f} ETH")
print(f"   Known OUT: {known_out:.6f} ETH")
print(f"   Computed:  {computed:.6f} ETH")
print(f"   On-chain:  {on_chain:.6f} ETH")
print(f"   GAP:       {gap:.6f} ETH")
print("="*60)
