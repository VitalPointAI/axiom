#!/usr/bin/env python3
"""Final reconciliation - match every tx"""
import requests
import os
import sqlite3

ETHERSCAN_KEY = os.environ.get('ETHERSCAN_API_KEY', '')
ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
alchemy_url = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()

print("="*60)
print("FINAL RECONCILIATION")
print("="*60)

# Get Etherscan data
response = requests.get('https://api.etherscan.io/v2/api', params={
    'chainid': 1, 'module': 'account', 'action': 'txlist',
    'address': address, 'startblock': 0, 'endblock': 99999999,
    'apikey': ETHERSCAN_KEY
})
eth_txs = response.json().get('result', [])

# Calculate Etherscan totals
eth_out_value = 0
eth_out_gas = 0
eth_in_value = 0

for tx in eth_txs:
    is_error = tx.get('isError', '0') == '1'
    val = int(tx['value']) / 1e18
    
    if tx['to'].lower() == address and not is_error:
        eth_in_value += val
    
    if tx['from'].lower() == address:
        if not is_error:
            eth_out_value += val
        # Gas always paid even on error
        eth_out_gas += (int(tx['gasUsed']) * int(tx['gasPrice'])) / 1e18

print(f"\nETHERSCAN Normal Transactions ({len(eth_txs)} txs):")
print(f"  IN (value):  {eth_in_value:.6f} ETH")
print(f"  OUT (value): {eth_out_value:.6f} ETH")
print(f"  OUT (gas):   {eth_out_gas:.6f} ETH")

# Internal transactions
response = requests.get('https://api.etherscan.io/v2/api', params={
    'chainid': 1, 'module': 'account', 'action': 'txlistinternal',
    'address': address, 'startblock': 0, 'endblock': 99999999,
    'apikey': ETHERSCAN_KEY
})
eth_internal = response.json().get('result', []) if response.json().get('status') == '1' else []

int_in = sum(int(tx['value']) / 1e18 for tx in eth_internal 
             if tx['to'].lower() == address and tx.get('isError', '0') == '0')
int_out = sum(int(tx['value']) / 1e18 for tx in eth_internal 
              if tx['from'].lower() == address and tx.get('isError', '0') == '0')

print(f"\nETHERSCAN Internal Transactions ({len(eth_internal)} txs):")
print(f"  IN:  {int_in:.6f} ETH")
print(f"  OUT: {int_out:.6f} ETH")

# Get on-chain balance
response = requests.post(alchemy_url, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'eth_getBalance', 'params': [address, 'latest']
})
on_chain = int(response.json().get('result', '0x0'), 16) / 1e18

# Total
total_in = eth_in_value + int_in
total_out = eth_out_value + int_out + eth_out_gas
computed = total_in - total_out

print(f"\n{'='*60}")
print(f"ETHERSCAN TOTALS:")
print(f"  Total IN:  {total_in:.6f} ETH")
print(f"  Total OUT: {total_out:.6f} ETH")
print(f"  Computed:  {computed:.6f} ETH")
print(f"  On-chain:  {on_chain:.6f} ETH")
print(f"  DIFF:      {on_chain - computed:.6f} ETH")
print(f"{'='*60}")

# Now compare with our indexed data
print("\nOUR INDEXED DATA:")
conn = sqlite3.connect('/home/deploy/neartax/neartax.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT direction, SUM(CAST(amount AS REAL)) 
    FROM transactions 
    WHERE wallet_id = 75 AND asset = 'ETH'
    GROUP BY direction
''')
our_data = dict(cursor.fetchall())
our_in = our_data.get('IN', 0)
our_out = our_data.get('OUT', 0)

print(f"  IN:  {our_in:.6f} ETH")
print(f"  OUT: {our_out:.6f} ETH")
print(f"  Computed: {our_in - our_out:.6f} ETH")

print(f"\nDISCREPANCY:")
print(f"  IN diff:  {our_in - total_in:.6f} ETH")
print(f"  OUT diff: {our_out - total_out:.6f} ETH")

if abs(on_chain - computed) < 0.0001:
    print("\n✅ ETHERSCAN DATA IS CORRECT - we need to fix our indexer")
