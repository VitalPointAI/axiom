#!/usr/bin/env python3
"""
Tax report generator for Canadian corporate taxes.

Generates:
1. Capital gains/losses summary
2. Income summary (staking rewards, etc)
3. Full transaction ledger
4. T1135 foreign property check
5. Koinly-compatible CSV export
"""

import csv
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection
from engine.acb import PortfolioACB


def generate_capital_gains_report(year, output_dir=None):
    """
    Generate capital gains/losses report for a tax year.
    
    Returns summary dict and writes CSV if output_dir provided.
    """
    # TODO: Build from actual transaction data
    # For now, return structure
    
    report = {
        'year': year,
        'total_proceeds': 0,
        'total_acb': 0,
        'total_gains': 0,
        'total_losses': 0,
        'net_gain_loss': 0,
        'taxable_amount': 0,  # 50% inclusion rate
        'dispositions': []
    }
    
    if output_dir:
        output_path = Path(output_dir) / f"capital_gains_{year}.csv"
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Date', 'Asset', 'Units', 'Proceeds (CAD)', 
                'ACB', 'Gain/Loss', 'Notes'
            ])
            for d in report['dispositions']:
                writer.writerow([
                    d.get('date'),
                    d.get('symbol'),
                    d.get('units'),
                    d.get('proceeds'),
                    d.get('acb'),
                    d.get('gain_loss'),
                    d.get('notes', '')
                ])
        print(f"Wrote: {output_path}")
    
    return report


def generate_income_report(year, output_dir=None):
    """
    Generate income report (staking rewards, airdrops, etc).
    
    In Canada, these are taxable as income at FMV when received.
    """
    conn = get_connection()
    
    # Get staking/income transactions from exchange imports
    rows = conn.execute("""
        SELECT tx_date, asset, quantity, total_value, tx_type, notes
        FROM exchange_transactions
        WHERE tx_type IN ('staking_reward', 'interest', 'reward', 'airdrop')
        AND strftime('%Y', tx_date) = ?
        ORDER BY tx_date
    """, (str(year),)).fetchall()
    
    conn.close()
    
    income_items = []
    total_income = 0
    
    for row in rows:
        item = {
            'date': row[0],
            'asset': row[1],
            'quantity': float(row[2] or 0),
            'fmv_cad': float(row[3] or 0),
            'type': row[4],
            'notes': row[5]
        }
        income_items.append(item)
        total_income += item['fmv_cad']
    
    report = {
        'year': year,
        'total_income': total_income,
        'items': income_items,
        'by_type': {}
    }
    
    # Group by type
    for item in income_items:
        tx_type = item['type']
        if tx_type not in report['by_type']:
            report['by_type'][tx_type] = {'count': 0, 'total': 0}
        report['by_type'][tx_type]['count'] += 1
        report['by_type'][tx_type]['total'] += item['fmv_cad']
    
    if output_dir:
        output_path = Path(output_dir) / f"income_{year}.csv"
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Date', 'Type', 'Asset', 'Quantity', 'FMV (CAD)', 'Notes'
            ])
            for item in income_items:
                writer.writerow([
                    item['date'],
                    item['type'],
                    item['asset'],
                    item['quantity'],
                    item['fmv_cad'],
                    item['notes'] or ''
                ])
        print(f"Wrote: {output_path}")
    
    return report


def generate_transaction_ledger(year=None, output_dir=None):
    """
    Generate full transaction ledger for audit trail.
    """
    conn = get_connection()
    
    # NEAR transactions
    query = """
        SELECT 'NEAR' as chain, w.account_id, t.tx_hash, t.block_timestamp,
               t.action_type, t.direction, t.counterparty, t.amount, t.fee
        FROM transactions t
        JOIN wallets w ON t.wallet_id = w.id
    """
    if year:
        # Filter by year (block_timestamp is in nanoseconds)
        start_ns = int(datetime(year, 1, 1).timestamp() * 1e9)
        end_ns = int(datetime(year + 1, 1, 1).timestamp() * 1e9)
        query += f" WHERE t.block_timestamp >= {start_ns} AND t.block_timestamp < {end_ns}"
    
    query += " ORDER BY t.block_timestamp"
    
    rows = conn.execute(query).fetchall()
    conn.close()
    
    ledger = []
    for row in rows:
        ledger.append({
            'chain': row[0],
            'account': row[1],
            'tx_hash': row[2],
            'timestamp': row[3],
            'action': row[4],
            'direction': row[5],
            'counterparty': row[6],
            'amount': row[7],
            'fee': row[8]
        })
    
    if output_dir:
        output_path = Path(output_dir) / f"ledger_{year or 'all'}.csv"
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Chain', 'Account', 'TX Hash', 'Timestamp',
                'Action', 'Direction', 'Counterparty', 'Amount', 'Fee'
            ])
            for item in ledger:
                writer.writerow([
                    item['chain'],
                    item['account'],
                    item['tx_hash'],
                    item['timestamp'],
                    item['action'],
                    item['direction'],
                    item['counterparty'],
                    item['amount'],
                    item['fee']
                ])
        print(f"Wrote: {output_path}")
    
    return ledger


def check_t1135_threshold(year, threshold_cad=100000):
    """
    Check if T1135 (Foreign Income Verification Statement) is required.
    
    Required if cost of specified foreign property > $100,000 CAD
    at any time during the year.
    
    Crypto held on non-Canadian exchanges is specified foreign property.
    """
    # TODO: Calculate max portfolio value during year
    # For now, return structure
    
    return {
        'year': year,
        'threshold': threshold_cad,
        'max_value': 0,  # TODO: calculate
        'required': False,
        'note': 'T1135 required if foreign property cost > $100,000 CAD'
    }


def export_koinly_format(year=None, output_dir=None):
    """
    Export transactions in Koinly-compatible CSV format.
    
    Koinly format columns:
    Date, Sent Amount, Sent Currency, Received Amount, Received Currency,
    Fee Amount, Fee Currency, Net Worth Amount, Net Worth Currency,
    Label, Description, TxHash
    """
    conn = get_connection()
    output_path = Path(output_dir or '.') / f"koinly_export_{year or 'all'}.csv"
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Date', 'Sent Amount', 'Sent Currency', 
            'Received Amount', 'Received Currency',
            'Fee Amount', 'Fee Currency',
            'Net Worth Amount', 'Net Worth Currency',
            'Label', 'Description', 'TxHash'
        ])
        
        # Export NEAR transactions
        rows = conn.execute("""
            SELECT t.block_timestamp, t.direction, t.amount, t.fee, 
                   t.action_type, t.tx_hash, w.account_id
            FROM transactions t
            JOIN wallets w ON t.wallet_id = w.id
            ORDER BY t.block_timestamp
        """).fetchall()
        
        for row in rows:
            timestamp = row[0]
            if timestamp:
                # Convert nanoseconds to datetime
                try:
                    date = datetime.fromtimestamp(int(timestamp) / 1e9).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    date = ''
            else:
                date = ''
            
            direction = row[1]
            amount = float(row[2] or 0) / 1e24  # yoctoNEAR to NEAR
            fee = float(row[3] or 0) / 1e24
            action = row[4]
            tx_hash = row[5]
            account = row[6]
            
            sent_amount = amount if direction == 'out' else ''
            sent_currency = 'NEAR' if direction == 'out' else ''
            received_amount = amount if direction == 'in' else ''
            received_currency = 'NEAR' if direction == 'in' else ''
            
            label = ''
            if action == 'STAKE':
                label = 'staking'
            elif action == 'UNSTAKE':
                label = 'unstaking'
            
            writer.writerow([
                date,
                sent_amount,
                sent_currency,
                received_amount,
                received_currency,
                fee if fee > 0 else '',
                'NEAR' if fee > 0 else '',
                '', '',  # Net worth
                label,
                f"{action} - {account}",
                tx_hash
            ])
        
        # Export exchange transactions
        rows = conn.execute("""
            SELECT tx_date, tx_type, asset, quantity, fee, fee_asset, 
                   total_value, currency, notes, tx_id
            FROM exchange_transactions
            ORDER BY tx_date
        """).fetchall()
        
        for row in rows:
            date = row[0]
            tx_type = row[1]
            asset = row[2]
            quantity = row[3]
            fee = row[4]
            fee_asset = row[5]
            total_value = row[6]
            currency = row[7]
            notes = row[8]
            tx_id = row[9]
            
            sent_amount = quantity if tx_type in ['sell', 'send'] else ''
            sent_currency = asset if tx_type in ['sell', 'send'] else ''
            received_amount = quantity if tx_type in ['buy', 'receive', 'staking_reward'] else ''
            received_currency = asset if tx_type in ['buy', 'receive', 'staking_reward'] else ''
            
            # For buys, we also receive fiat worth
            if tx_type == 'sell' and total_value:
                received_amount = total_value
                received_currency = currency
            elif tx_type == 'buy' and total_value:
                sent_amount = total_value
                sent_currency = currency
            
            label = tx_type
            if tx_type == 'staking_reward':
                label = 'reward'
            
            writer.writerow([
                date,
                sent_amount,
                sent_currency,
                received_amount,
                received_currency,
                fee or '',
                fee_asset or '',
                '', '',
                label,
                notes or '',
                tx_id or ''
            ])
    
    conn.close()
    print(f"Wrote: {output_path}")
    return str(output_path)


def generate_all_reports(year, output_dir):
    """Generate all tax reports for a year."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nGenerating tax reports for {year}...")
    print(f"Output directory: {output_dir}")
    print("-" * 50)
    
    # Capital gains
    cg = generate_capital_gains_report(year, output_dir)
    print(f"Capital Gains: {cg['net_gain_loss']:.2f} CAD")
    
    # Income
    inc = generate_income_report(year, output_dir)
    print(f"Income: {inc['total_income']:.2f} CAD")
    
    # Ledger
    ledger = generate_transaction_ledger(year, output_dir)
    print(f"Transaction Ledger: {len(ledger)} entries")
    
    # T1135 check
    t1135 = check_t1135_threshold(year)
    print(f"T1135 Required: {t1135['required']}")
    
    # Koinly export
    koinly_path = export_koinly_format(year, output_dir)
    print(f"Koinly Export: {koinly_path}")
    
    print("-" * 50)
    print("Reports generated successfully!")
    
    return {
        'capital_gains': cg,
        'income': inc,
        'ledger_entries': len(ledger),
        't1135': t1135,
        'koinly_export': koinly_path
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate tax reports")
    parser.add_argument("--year", type=int, default=2025, help="Tax year")
    parser.add_argument("--output", "-o", default="./output", help="Output directory")
    
    args = parser.parse_args()
    
    generate_all_reports(args.year, args.output)
