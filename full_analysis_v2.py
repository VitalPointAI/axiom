#!/usr/bin/env python3
"""Full transaction reconciliation v2 - correct gas calculation"""
import requests
import os

ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
ETHERSCAN_KEY = os.environ.get('ETHERSCAN_API_KEY', '')
url = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()

print("="*60)
print("FULL TRANSACTION RECONCILIATION v2")
print("="*60)

# Use Etherscan to get ALL normal transactions (includes gas data)
print("\n1. Fetching from Etherscan (normal + internal)...")

# Normal txs
response = requests.get('https://api.etherscan.io/v2/api', params={
    'chainid': 1,
    'module': 'account',
    'action': 'txlist',
    'address': address,
    'startblock': 0,
    'endblock': 99999999,
    'sort': 'asc',
    'apikey': ETHERSCAN_KEY
})
normal_txs = response.json().get('result', [])
print(f"   Normal txs: {len(normal_txs)}")

# Internal txs
response = requests.get('https://api.etherscan.io/v2/api', params={
    'chainid': 1,
    'module': 'account',
    'action': 'txlistinternal',
    'address': address,
    'startblock': 0,
    'endblock': 99999999,
    'sort': 'asc',
    'apikey': ETHERSCAN_KEY
})
internal_txs = response.json().get('result', []) if response.json().get('status') == '1' else []
print(f"   Internal txs: {len(internal_txs)}")

# Calculate
eth_in_normal = sum(int(tx['value']) / 1e18 for tx in normal_txs
                    if tx['to'].lower() == address and tx.get('isError', '0') == '0')
eth_out_normal = sum(int(tx['value']) / 1e18 for tx in normal_txs
                     if tx['from'].lower() == address and tx.get('isError', '0') == '0')
eth_in_internal = sum(int(tx['value']) / 1e18 for tx in internal_txs
                      if tx['to'].lower() == address and tx.get('isError', '0') == '0')
eth_out_internal = sum(int(tx['value']) / 1e18 for tx in internal_txs
                       if tx['from'].lower() == address and tx.get('isError', '0') == '0')

# Gas fees - only for txs we initiated
gas_fees = sum((int(tx['gasUsed']) * int(tx['gasPrice'])) / 1e18
               for tx in normal_txs if tx['from'].lower() == address)

print(f"\n   Normal IN:    {eth_in_normal:.6f} ETH")
print(f"   Normal OUT:   {eth_out_normal:.6f} ETH")
print(f"   Internal IN:  {eth_in_internal:.6f} ETH")
print(f"   Internal OUT: {eth_out_internal:.6f} ETH")
print(f"   Gas fees:     {gas_fees:.6f} ETH")

total_in = eth_in_normal + eth_in_internal
total_out = eth_out_normal + eth_out_internal + gas_fees

# Get on-chain balance
response = requests.post(url, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'eth_getBalance',
    'params': [address, 'latest']
})
on_chain = int(response.json().get('result', '0x0'), 16) / 1e18

computed = total_in - total_out
gap = on_chain - computed

print("\n" + "="*60)
print("ETHERSCAN RECONCILIATION:")
print("="*60)
print(f"   Total IN:   {total_in:.6f} ETH")
print(f"   Total OUT:  {total_out:.6f} ETH (incl gas)")
print(f"   Computed:   {computed:.6f} ETH")
print(f"   On-chain:   {on_chain:.6f} ETH")
print(f"   GAP:        {gap:.6f} ETH")
print("="*60)

# Now check for things Etherscan might miss
print("\n2. Checking for missing internal txs via Alchemy traces...")

response = requests.post(url, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'trace_filter',
    'params': [{
        'toAddress': [address],
        'fromBlock': 'earliest',
        'toBlock': 'latest'
    }]
}, timeout=120)

alchemy_traces_in = response.json().get('result', [])
alchemy_in_value = sum(int(t.get('action', {}).get('value', '0x0'), 16) / 1e18
                       for t in alchemy_traces_in)
print(f"   Alchemy trace IN: {alchemy_in_value:.6f} ETH ({len(alchemy_traces_in)} traces)")

# Compare with Etherscan internal
extra_from_traces = alchemy_in_value - eth_in_internal
print(f"   Extra vs Etherscan internal: {extra_from_traces:.6f} ETH")

# Final calculation including trace extras
final_in = total_in + max(0, extra_from_traces)
final_computed = final_in - total_out
final_gap = on_chain - final_computed

print("\n" + "="*60)
print("FINAL RECONCILIATION (with traces):")
print("="*60)
print(f"   Total IN:   {final_in:.6f} ETH")
print(f"   Total OUT:  {total_out:.6f} ETH")
print(f"   Computed:   {final_computed:.6f} ETH")
print(f"   On-chain:   {on_chain:.6f} ETH")
print(f"   GAP:        {final_gap:.6f} ETH")
print("="*60)

if abs(final_gap) < 0.01:
    print("\n✅ BALANCED!")
else:
    print(f"\n⚠️  Still missing {final_gap:.6f} ETH")
    print("\nPossible sources:")
    print("  - Mining/staking rewards")
    print("  - Airdrop from contract without transfer event")
    print("  - Pre-merge PoW block rewards")
    print("  - Very early tx before indexing coverage")
