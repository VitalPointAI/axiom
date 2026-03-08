#!/usr/bin/env python3
"""Check for WETH wrap/unwrap that might explain the gap"""
import requests
import os
import sqlite3

ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
url = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()
weth = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'.lower()  # WETH contract

print("Checking WETH interactions...")

# Check for ETH sent to WETH (wrapping)
conn = sqlite3.connect('/home/deploy/neartax/neartax.db')
cursor = conn.cursor()

# Get all ETH transfers TO WETH contract
cursor.execute('''
    SELECT tx_hash, amount, action_type
    FROM transactions 
    WHERE wallet_id = 75 
    AND direction = 'OUT' 
    AND asset = 'ETH'
    AND LOWER(counterparty) = ?
''', (weth,))

weth_out = cursor.fetchall()
total_wrapped = sum(float(r[1]) for r in weth_out)
print(f"\nETH sent to WETH (wrapping): {len(weth_out)} txs, {total_wrapped:.6f} ETH")

# Get WETH token transfers 
cursor.execute('''
    SELECT tx_hash, amount, direction, action_type
    FROM transactions 
    WHERE wallet_id = 75 
    AND asset = 'WETH'
''')
weth_transfers = cursor.fetchall()
print(f"WETH token transfers: {len(weth_transfers)}")

weth_in = sum(float(r[1]) for r in weth_transfers if r[2] == 'IN')
weth_out_amt = sum(float(r[1]) for r in weth_transfers if r[2] == 'OUT')
print(f"  WETH IN:  {weth_in:.6f}")
print(f"  WETH OUT: {weth_out_amt:.6f}")

# Now use Alchemy to check for ANY interaction with WETH
print("\n\nChecking Alchemy for WETH transfers...")
response = requests.post(url, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'alchemy_getAssetTransfers',
    'params': [{
        'toAddress': address,
        'contractAddresses': [weth],
        'category': ['erc20'],
        'withMetadata': True,
        'excludeZeroValue': False
    }]
})
weth_to = response.json().get('result', {}).get('transfers', [])
print(f"WETH incoming: {len(weth_to)}")
weth_to_total = sum(t.get('value') or 0 for t in weth_to)
print(f"  Total: {weth_to_total:.6f} WETH")

response = requests.post(url, json={
    'jsonrpc': '2.0', 'id': 1,
    'method': 'alchemy_getAssetTransfers',
    'params': [{
        'fromAddress': address,
        'contractAddresses': [weth],
        'category': ['erc20'],
        'withMetadata': True,
        'excludeZeroValue': False
    }]
})
weth_from = response.json().get('result', {}).get('transfers', [])
print(f"WETH outgoing: {len(weth_from)}")
weth_from_total = sum(t.get('value') or 0 for t in weth_from)
print(f"  Total: {weth_from_total:.6f} WETH")

# Check for failed transactions (paid gas but value refunded)
print("\n\nChecking for failed transactions...")
cursor.execute('''
    SELECT COUNT(*), SUM(CAST(amount AS REAL))
    FROM transactions 
    WHERE wallet_id = 75 
    AND success = 0
''')
failed = cursor.fetchone()
print(f"Failed txs: {failed[0]}, Value: {failed[1] or 0:.6f} ETH")

# Check ALL unique counterparties for major OUT flows
print("\n\nTop 10 counterparties (OUT):")
cursor.execute('''
    SELECT counterparty, SUM(CAST(amount AS REAL)) as total, COUNT(*)
    FROM transactions 
    WHERE wallet_id = 75 
    AND direction = 'OUT'
    AND asset = 'ETH'
    GROUP BY counterparty
    ORDER BY total DESC
    LIMIT 10
''')
for row in cursor.fetchall():
    print(f"  {row[0][:20]}...: {row[1]:.4f} ETH ({row[2]} txs)")

conn.close()
