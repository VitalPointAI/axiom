#!/usr/bin/env python3
"""Check Etherscan for all transactions"""
import os
import requests

ETHERSCAN_KEY = os.environ.get('ETHERSCAN_API_KEY', '')
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()

print("Fetching all transactions from Etherscan...")

# Normal transactions (V2 API)
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

data = response.json()
if data.get('status') != '1':
    print(f"Error: {data}")
    exit(1)

txs = data.get('result', [])
print(f"Normal transactions: {len(txs)}")

# Calculate totals
total_in = 0
total_out = 0 
total_gas = 0

for tx in txs:
    val = int(tx.get('value', '0')) / 1e18
    
    if tx.get('to', '').lower() == address:
        total_in += val
    if tx.get('from', '').lower() == address:
        total_out += val
        # Add gas
        gas_used = int(tx.get('gasUsed', '0'))
        gas_price = int(tx.get('gasPrice', '0'))
        total_gas += (gas_used * gas_price) / 1e18

print("\nNormal tx totals:")
print(f"  IN:  {total_in:.6f} ETH")
print(f"  OUT: {total_out:.6f} ETH")
print(f"  GAS: {total_gas:.6f} ETH")

# Internal transactions (V2 API)
response2 = requests.get('https://api.etherscan.io/v2/api', params={
    'chainid': 1,
    'module': 'account',
    'action': 'txlistinternal',
    'address': address,
    'startblock': 0,
    'endblock': 99999999,
    'sort': 'asc',
    'apikey': ETHERSCAN_KEY
})

data2 = response2.json()
internal_txs = data2.get('result', []) if data2.get('status') == '1' else []
print(f"\nInternal transactions: {len(internal_txs)}")

internal_in = 0
internal_out = 0

for tx in internal_txs:
    val = int(tx.get('value', '0')) / 1e18
    if tx.get('to', '').lower() == address:
        internal_in += val
    if tx.get('from', '').lower() == address:
        internal_out += val

print(f"  IN:  {internal_in:.6f} ETH")
print(f"  OUT: {internal_out:.6f} ETH")

# Grand totals
grand_in = total_in + internal_in
grand_out = total_out + internal_out + total_gas

print(f"\n{'='*50}")
print("ETHERSCAN TOTALS:")
print(f"  Total IN:  {grand_in:.6f} ETH")
print(f"  Total OUT: {grand_out:.6f} ETH (incl gas)")
print(f"  Computed:  {grand_in - grand_out:.6f} ETH")

# First funding transaction
print("\nFirst transactions:")
for tx in txs[:3]:
    val = int(tx.get('value', '0')) / 1e18
    from_addr = tx.get('from', '')[:16]
    to_addr = tx.get('to', '')[:16]
    block = tx.get('blockNumber')
    print(f"  Block {block}: {from_addr} -> {to_addr} ({val:.6f} ETH)")
