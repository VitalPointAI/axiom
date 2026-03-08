#!/usr/bin/env python3
"""Full transaction reconciliation"""
import requests
import os

ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
url = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()

print("="*60)
print("FULL TRANSACTION RECONCILIATION")
print("="*60)

# Get ALL incoming transfers from Alchemy
print("\n1. Fetching ALL incoming ETH transfers...")
all_in = []
page_key = None
while True:
    params = {
        'toAddress': address,
        'category': ['external', 'internal'],
        'withMetadata': True,
        'excludeZeroValue': False
    }
    if page_key:
        params['pageKey'] = page_key
        
    response = requests.post(url, json={
        'jsonrpc': '2.0', 'id': 1,
        'method': 'alchemy_getAssetTransfers',
        'params': [params]
    })
    
    result = response.json().get('result', {})
    all_in.extend(result.get('transfers', []))
    page_key = result.get('pageKey')
    if not page_key:
        break

eth_in = [t for t in all_in if t.get('asset') == 'ETH']
total_in = sum(t.get('value') or 0 for t in eth_in)
print(f"   Found {len(eth_in)} ETH incoming transfers")
print(f"   Total: {total_in:.6f} ETH")

# Get ALL outgoing transfers
print("\n2. Fetching ALL outgoing ETH transfers...")
all_out = []
page_key = None
while True:
    params = {
        'fromAddress': address,
        'category': ['external', 'internal'],
        'withMetadata': True,
        'excludeZeroValue': False
    }
    if page_key:
        params['pageKey'] = page_key
        
    response = requests.post(url, json={
        'jsonrpc': '2.0', 'id': 1,
        'method': 'alchemy_getAssetTransfers',
        'params': [params]
    })
    
    result = response.json().get('result', {})
    all_out.extend(result.get('transfers', []))
    page_key = result.get('pageKey')
    if not page_key:
        break

eth_out = [t for t in all_out if t.get('asset') == 'ETH']
total_out = sum(t.get('value') or 0 for t in eth_out)
print(f"   Found {len(eth_out)} ETH outgoing transfers")
print(f"   Total: {total_out:.6f} ETH")

# Get gas fees by fetching ALL transactions receipts
print("\n3. Calculating total gas fees...")

# Get unique tx hashes where we're the sender
out_tx_hashes = set(t.get('hash') for t in eth_out)

# Also get internal txs we initiated
all_internal_out = [t for t in all_out if t.get('category') == 'internal']
print(f"   Internal outgoing: {len(all_internal_out)}")

# For gas, we need ALL transactions FROM this address
# Use trace_filter to get transaction list
response = requests.post(url, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'trace_filter',
    'params': [{
        'fromAddress': [address],
        'fromBlock': 'earliest',
        'toBlock': 'latest'
    }]
}, timeout=120)

traces = response.json().get('result', [])
tx_hashes = set(t.get('transactionHash') for t in traces)
print(f"   Unique outgoing txs (from traces): {len(tx_hashes)}")

# Batch fetch receipts
total_gas = 0
for i in range(0, len(tx_hashes), 50):
    batch = list(tx_hashes)[i:i+50]
    for tx_hash in batch:
        response = requests.post(url, json={
            'jsonrpc': '2.0', 'id': 1,
            'method': 'eth_getTransactionReceipt',
            'params': [tx_hash]
        })
        receipt = response.json().get('result')
        if receipt:
            gas_used = int(receipt.get('gasUsed', '0x0'), 16)
            gas_price = int(receipt.get('effectiveGasPrice', '0x0'), 16)
            fee = (gas_used * gas_price) / 1e18
            total_gas += fee

print(f"   Total gas: {total_gas:.6f} ETH")

# Get on-chain balance
response = requests.post(url, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'eth_getBalance',
    'params': [address, 'latest']
})
on_chain = int(response.json().get('result', '0x0'), 16) / 1e18

# Calculate
computed = total_in - total_out - total_gas
gap = on_chain - computed

print("\n" + "="*60)
print("RECONCILIATION:")
print("="*60)
print(f"   IN (transfers):  {total_in:.6f} ETH")
print(f"   OUT (transfers): {total_out:.6f} ETH")
print(f"   OUT (gas):       {total_gas:.6f} ETH")
print(f"   Computed:        {computed:.6f} ETH")
print(f"   On-chain:        {on_chain:.6f} ETH")
print(f"   GAP:             {gap:.6f} ETH")
print("="*60)

if abs(gap) > 0.01:
    print(f"\n⚠️  Gap of {gap:.6f} ETH still unexplained!")
else:
    print(f"\n✅ Accounts balanced within tolerance!")
