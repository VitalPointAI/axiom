#!/usr/bin/env python3
"""Find and fix over-counted transfers"""
import requests
import os
import sqlite3

ETHERSCAN_KEY = os.environ.get('ETHERSCAN_API_KEY', '')
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()

print("Finding over-counted transfers...")

# Get Etherscan normal txs - the ground truth for external transfers
response = requests.get('https://api.etherscan.io/v2/api', params={
    'chainid': 1, 'module': 'account', 'action': 'txlist',
    'address': address, 'startblock': 0, 'endblock': 99999999,
    'apikey': ETHERSCAN_KEY
})
eth_txs = response.json().get('result', [])

# Build set of valid outgoing tx hashes and their values
valid_out = {}
for tx in eth_txs:
    if tx['from'].lower() == address and tx.get('isError', '0') == '0':
        val = int(tx['value']) / 1e18
        valid_out[tx['hash'].lower()] = val

print(f"Etherscan valid OUT txs: {len(valid_out)}")
print(f"Etherscan OUT total: {sum(valid_out.values()):.6f} ETH")

# Get our indexed transfers
conn = sqlite3.connect('/home/deploy/neartax/neartax.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT tx_hash, CAST(amount AS REAL), action_type
    FROM transactions 
    WHERE wallet_id = 75 AND direction = 'OUT' AND asset = 'ETH' AND action_type = 'TRANSFER'
''')
our_transfers = cursor.fetchall()

print(f"\nOur indexed TRANSFER OUT: {len(our_transfers)} txs")
print(f"Our OUT total: {sum(r[1] for r in our_transfers):.6f} ETH")

# Find transfers we have that DON'T match Etherscan
print(f"\n{'='*60}")
print("OVER-COUNTED (should be INTERNAL_TRANSFER or removed):")
print("="*60)

over_counted = []
for tx_hash, amount, action_type in our_transfers:
    clean_hash = tx_hash.lower()
    eth_val = valid_out.get(clean_hash, None)
    
    if eth_val is None:
        # We have it but Etherscan doesn't - it's an internal transfer
        print(f"  INTERNAL: {tx_hash[:40]}... {amount:.6f} ETH")
        over_counted.append((tx_hash, amount, 'not_in_etherscan'))
    elif abs(eth_val - amount) > 0.0001:
        # Value mismatch
        print(f"  MISMATCH: {tx_hash[:40]}... ours={amount:.6f} eth={eth_val:.6f}")
        over_counted.append((tx_hash, amount - eth_val, 'value_mismatch'))

total_over = sum(r[1] for r in over_counted)
print(f"\nTotal over-counted: {total_over:.6f} ETH")

# Fix by re-categorizing these as INTERNAL_TRANSFER
print(f"\n{'='*60}")
print("FIXING DATABASE...")
print("="*60)

for tx_hash, amount, reason in over_counted:
    if reason == 'not_in_etherscan':
        # Change to INTERNAL_TRANSFER
        cursor.execute('''
            UPDATE transactions 
            SET action_type = 'INTERNAL_TRANSFER'
            WHERE tx_hash = ? AND wallet_id = 75
        ''', (tx_hash,))
        print(f"  Updated {tx_hash[:30]}... to INTERNAL_TRANSFER")

conn.commit()

# Verify fix
cursor.execute('''
    SELECT direction, SUM(CAST(amount AS REAL)) 
    FROM transactions 
    WHERE wallet_id = 75 AND asset = 'ETH'
    AND action_type NOT IN ('INTERNAL_TRANSFER')
    GROUP BY direction
''')
fixed_data = dict(cursor.fetchall())

print(f"\nAFTER FIX (excluding INTERNAL_TRANSFER):")
print(f"  IN:  {fixed_data.get('IN', 0):.6f} ETH")
print(f"  OUT: {fixed_data.get('OUT', 0):.6f} ETH")
print(f"  Computed: {fixed_data.get('IN', 0) - fixed_data.get('OUT', 0):.6f} ETH")

conn.close()
