#!/usr/bin/env python3
"""Find double-counted outgoing transactions"""
import requests
import os
import sqlite3

ETHERSCAN_KEY = os.environ.get('ETHERSCAN_API_KEY', '')
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()

print("Finding double-counted transactions...")

# Get Etherscan normal txs (ground truth)
response = requests.get('https://api.etherscan.io/v2/api', params={
    'chainid': 1,
    'module': 'account',
    'action': 'txlist',
    'address': address,
    'startblock': 0,
    'endblock': 99999999,
    'apikey': ETHERSCAN_KEY
})
normal_txs = response.json().get('result', [])

# Build map of outgoing value by tx hash
etherscan_out = {}
for tx in normal_txs:
    if tx['from'].lower() == address and tx.get('isError', '0') == '0':
        val = int(tx['value']) / 1e18
        etherscan_out[tx['hash'].lower()] = val

print(f"Etherscan OUT txs: {len(etherscan_out)}")
print(f"Etherscan OUT total: {sum(etherscan_out.values()):.6f} ETH")

# Get our indexed data
conn = sqlite3.connect('/home/deploy/neartax/neartax.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT tx_hash, amount, action_type
    FROM transactions
    WHERE wallet_id = 75
    AND direction = 'OUT'
    AND asset = 'ETH'
    AND action_type != 'FEE'
''')
our_out = cursor.fetchall()

# Build map
our_out_map = {}
for tx_hash, amount, action_type in our_out:
    # Clean the hash (remove _fee suffix if present)
    clean_hash = tx_hash.replace('_fee', '').lower()
    if clean_hash not in our_out_map:
        our_out_map[clean_hash] = {'total': 0, 'types': []}
    our_out_map[clean_hash]['total'] += float(amount)
    our_out_map[clean_hash]['types'].append(action_type)

print(f"\nOur OUT txs: {len(our_out_map)}")
print(f"Our OUT total: {sum(d['total'] for d in our_out_map.values()):.6f} ETH")

# Find discrepancies
print("\n" + "="*60)
print("Transactions with different values:")
print("="*60)

for tx_hash, our_data in our_out_map.items():
    eth_val = etherscan_out.get(tx_hash, 0)
    our_val = our_data['total']

    if abs(eth_val - our_val) > 0.0001:
        diff = our_val - eth_val
        print(f"\n{tx_hash[:20]}...")
        print(f"  Etherscan: {eth_val:.6f} ETH")
        print(f"  Ours:      {our_val:.6f} ETH (types: {our_data['types']})")
        print(f"  OVER:      {diff:.6f} ETH")

# Find txs we have that Etherscan doesn't
print("\n" + "="*60)
print("Txs we have but Etherscan doesn't (internal out):")
print("="*60)
internal_out = 0
for tx_hash, our_data in our_out_map.items():
    if tx_hash not in etherscan_out:
        print(f"  {tx_hash[:30]}... = {our_data['total']:.6f} ETH ({our_data['types']})")
        internal_out += our_data['total']

print(f"\nTotal internal OUT: {internal_out:.6f} ETH")

conn.close()
