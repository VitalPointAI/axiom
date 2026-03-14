#!/usr/bin/env python3
"""Calculate and store ETH transaction fees using Alchemy."""

import requests
import sqlite3

ALCHEMY_API_KEY = 'ckTIZT8on08E5QxyY8oOw'
ALCHEMY_URL = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'
wallet_id = 75

# Get all outbound external txs
response = requests.post(ALCHEMY_URL, json={
    'jsonrpc': '2.0',
    'id': 1,
    'method': 'alchemy_getAssetTransfers',
    'params': [{
        'fromAddress': address.lower(),
        'category': ['external'],
        'withMetadata': True,
        'maxCount': '0x3e8',
    }]
}, timeout=30)

transfers = response.json().get('result', {}).get('transfers', [])
print(f'Processing {len(transfers)} outbound transactions for fees...')

with sqlite3.connect('/home/deploy/neartax/neartax.db') as conn:
    cursor = conn.cursor()
    try:
        total_fees = 0
        for t in transfers:
            tx_hash = t.get('hash')
            r = requests.post(ALCHEMY_URL, json={
                'jsonrpc': '2.0', 'id': 1,
                'method': 'eth_getTransactionReceipt',
                'params': [tx_hash]
            })
            receipt = r.json().get('result', {})
            if not receipt:
                continue
            gas_used = int(receipt.get('gasUsed', '0x0'), 16)
            gas_price = int(receipt.get('effectiveGasPrice', '0x0'), 16)
            fee = (gas_used * gas_price) / 1e18
            total_fees += fee

            # Update fee in DB
            cursor.execute('UPDATE transactions SET fee = ? WHERE tx_hash = ? AND wallet_id = ?',
                           (str(fee), tx_hash, wallet_id))

        conn.commit()
        print(f'Total fees: {total_fees:.6f} ETH')

        # Recalculate balance
        cursor.execute('''
            SELECT
                SUM(CASE WHEN direction = 'IN' THEN CAST(amount AS REAL) ELSE 0 END) as total_in,
                SUM(CASE WHEN direction = 'OUT' THEN CAST(amount AS REAL) ELSE 0 END) as total_out,
                SUM(CAST(COALESCE(fee, 0) AS REAL)) as total_fees
            FROM transactions WHERE wallet_id = ?
        ''', (wallet_id,))
        row = cursor.fetchone()
        total_in = row[0] or 0
        total_out = row[1] or 0
        db_fees = row[2] or 0
        computed = total_in - total_out - db_fees

        print('\nFinal verification:')
        print(f'  IN: {total_in:.6f} ETH')
        print(f'  OUT: {total_out:.6f} ETH')
        print(f'  Fees: {db_fees:.6f} ETH')
        print(f'  Computed: {computed:.6f} ETH')

        # Get on-chain balance
        r = requests.post(ALCHEMY_URL, json={
            'jsonrpc': '2.0', 'id': 1,
            'method': 'eth_getBalance',
            'params': [address, 'latest']
        })
        on_chain = int(r.json()['result'], 16) / 1e18
        diff = abs(on_chain - computed)
        print(f'  On-chain: {on_chain:.6f} ETH')
        print(f'  Diff: {diff:.6f} ETH (${diff * 4800:.0f} CAD)')

        if diff < 0.01:
            print('\n✅ MATCH! Balance verified within 0.01 ETH')
        else:
            print(f'\n⚠️ Still {diff:.4f} ETH difference - may be ERC-20 swaps affecting ETH balance')
    finally:
        cursor.close()
