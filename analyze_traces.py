#!/usr/bin/env python3
"""Full trace analysis to find missing ETH"""
import requests
import os
import json

ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY', '')
url = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
address = '0x55b8e2c4ae5951d1a8e77d0e513a6e598ee0be86'.lower()

def fetch_all_traces(direction):
    """Fetch all traces with pagination"""
    all_traces = []
    after = None
    
    while True:
        params = {
            f'{direction}Address': [address],
            'fromBlock': 'earliest',
            'toBlock': 'latest',
            'count': 1000
        }
        if after:
            params['after'] = after
            
        response = requests.post(url, json={
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'trace_filter',
            'params': [params]
        }, timeout=60)
        
        data = response.json()
        if 'error' in data:
            print(f"Error: {data['error']}")
            break
            
        traces = data.get('result', [])
        all_traces.extend(traces)
        
        if len(traces) < 1000:
            break
        after = len(all_traces)
    
    return all_traces

print(f"Analyzing traces for {address[:16]}...")
print("="*60)

# Fetch incoming traces
print("\nFetching incoming traces...")
incoming = fetch_all_traces('to')
print(f"Got {len(incoming)} incoming traces")

# Fetch outgoing traces  
print("\nFetching outgoing traces...")
outgoing = fetch_all_traces('from')
print(f"Got {len(outgoing)} outgoing traces")

# Analyze incoming
print("\n" + "="*60)
print("INCOMING ANALYSIS:")
print("="*60)

incoming_by_type = {}
incoming_total = 0

for t in incoming:
    trace_type = t.get('type', 'unknown')
    action = t.get('action', {})
    
    # Get value depending on type
    if trace_type == 'suicide':
        value = int(action.get('balance', '0x0'), 16) / 1e18
    elif trace_type == 'create':
        value = int(action.get('value', '0x0'), 16) / 1e18
    else:
        value = int(action.get('value', '0x0'), 16) / 1e18
    
    if trace_type not in incoming_by_type:
        incoming_by_type[trace_type] = {'count': 0, 'value': 0}
    incoming_by_type[trace_type]['count'] += 1
    incoming_by_type[trace_type]['value'] += value
    incoming_total += value

for t_type, data in sorted(incoming_by_type.items(), key=lambda x: -x[1]['value']):
    print(f"  {t_type}: {data['count']} traces, {data['value']:.6f} ETH")

print(f"\nTotal incoming from traces: {incoming_total:.6f} ETH")

# Analyze outgoing
print("\n" + "="*60)
print("OUTGOING ANALYSIS:")
print("="*60)

outgoing_by_type = {}
outgoing_total = 0

for t in outgoing:
    trace_type = t.get('type', 'unknown')
    action = t.get('action', {})
    
    if trace_type == 'suicide':
        value = int(action.get('balance', '0x0'), 16) / 1e18
    else:
        value = int(action.get('value', '0x0'), 16) / 1e18
    
    if trace_type not in outgoing_by_type:
        outgoing_by_type[trace_type] = {'count': 0, 'value': 0}
    outgoing_by_type[trace_type]['count'] += 1
    outgoing_by_type[trace_type]['value'] += value
    outgoing_total += value

for t_type, data in sorted(outgoing_by_type.items(), key=lambda x: -x[1]['value']):
    print(f"  {t_type}: {data['count']} traces, {data['value']:.6f} ETH")

print(f"\nTotal outgoing from traces: {outgoing_total:.6f} ETH")

# Compare with what we have
print("\n" + "="*60)
print("COMPARISON:")
print("="*60)

# From verify output:
current_in = 22.072201
current_out = 24.306743
on_chain = 0.241848

trace_computed = incoming_total - outgoing_total
print(f"Trace IN:  {incoming_total:.6f} ETH")
print(f"Trace OUT: {outgoing_total:.6f} ETH")
print(f"Trace computed balance: {trace_computed:.6f} ETH")
print(f"On-chain balance: {on_chain:.6f} ETH")
print(f"Difference: {on_chain - trace_computed:.6f} ETH")

print(f"\nOur indexed IN:  {current_in:.6f} ETH")
print(f"Our indexed OUT: {current_out:.6f} ETH")
print(f"Missing IN:  {incoming_total - current_in:.6f} ETH")
print(f"Missing OUT: {outgoing_total - current_out:.6f} ETH")
