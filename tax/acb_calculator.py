#!/usr/bin/env python3
"""
Adjusted Cost Base (ACB) Calculator for Canadian Crypto Taxes

Uses the "average cost method" (superficial pooling) required by CRA:
- All units of the same property are pooled together
- ACB is the total cost / total units
- On disposal, reduce ACB proportionally

For crypto:
- Each token is a separate property pool
- Track acquisitions and disposals chronologically
- Calculate gain/loss on each disposal
"""

import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Dict, List, Tuple
from dataclasses import dataclass

@dataclass
class TaxLot:
    """Represents a pool of identical property (token)"""
    token: str
    total_units: Decimal
    total_cost_cad: Decimal
    
    @property
    def acb_per_unit(self) -> Decimal:
        if self.total_units == 0:
            return Decimal('0')
        return (self.total_cost_cad / self.total_units).quantize(Decimal('0.00000001'))
    
    def add(self, units: Decimal, cost_cad: Decimal):
        """Add units to the pool (acquisition)"""
        self.total_units += units
        self.total_cost_cad += cost_cad
    
    def remove(self, units: Decimal) -> Tuple[Decimal, Decimal]:
        """Remove units from pool (disposal), returns (acb_of_disposed, remaining_acb)"""
        if units > self.total_units:
            units = self.total_units  # Can't dispose more than we have
        
        acb_per = self.acb_per_unit
        disposed_acb = (units * acb_per).quantize(Decimal('0.01'), ROUND_HALF_UP)
        
        self.total_units -= units
        self.total_cost_cad -= disposed_acb
        
        # Prevent negative due to rounding
        if self.total_cost_cad < 0:
            self.total_cost_cad = Decimal('0')
        
        return disposed_acb, self.total_cost_cad


def calculate_acb(db_path: str = 'neartax.db', year: int = 2025) -> Dict:
    """
    Calculate ACB and capital gains for all tokens
    
    Returns summary of gains/losses by year
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Token pools - keyed by token symbol
    pools: Dict[str, TaxLot] = {}
    
    # Get NEAR pool from transactions
    pools['NEAR'] = TaxLot(token='NEAR', total_units=Decimal('0'), total_cost_cad=Decimal('0'))
    
    # Process all transactions chronologically
    cur.execute('''
        SELECT 
            t.id,
            t.tx_hash,
            t.direction,
            t.action_type,
            t.tax_category,
            CAST(t.amount AS REAL) / 1e24 as amount_near,
            t.cost_basis_usd,
            t.cost_basis_cad,
            t.block_timestamp,
            w.account_id
        FROM transactions t
        LEFT JOIN wallets w ON t.wallet_id = w.id
        WHERE t.amount IS NOT NULL AND CAST(t.amount AS REAL) > 0
        ORDER BY t.block_timestamp ASC
    ''')
    
    transactions = cur.fetchall()
    
    # Track disposals for capital gains
    disposals: List[Dict] = []
    acquisitions: List[Dict] = []
    
    for tx in transactions:
        amount = Decimal(str(tx['amount_near'] or 0))
        if amount <= 0:
            continue
            
        # Get cost in CAD
        cost_cad = Decimal(str(tx['cost_basis_cad'] or 0))
        if cost_cad == 0 and tx['cost_basis_usd']:
            cost_cad = Decimal(str(tx['cost_basis_usd'])) * Decimal('1.35')
        
        timestamp = tx['block_timestamp']
        tx_date = datetime.utcfromtimestamp(timestamp / 1_000_000_000) if timestamp else None
        
        if tx['direction'] == 'in':
            # Acquisition - add to pool
            pools['NEAR'].add(amount, cost_cad)
            acquisitions.append({
                'tx_hash': tx['tx_hash'],
                'date': tx_date.isoformat() if tx_date else None,
                'amount': float(amount),
                'cost_cad': float(cost_cad),
                'acb_after': float(pools['NEAR'].acb_per_unit),
                'pool_total': float(pools['NEAR'].total_units)
            })
        
        elif tx['direction'] == 'out':
            # Disposal - calculate gain/loss
            proceeds_cad = cost_cad  # Proceeds = fair market value at time of disposal
            
            acb_disposed, _ = pools['NEAR'].remove(amount)
            gain_loss = proceeds_cad - acb_disposed
            
            disposals.append({
                'id': tx['id'],
                'tx_hash': tx['tx_hash'],
                'date': tx_date.isoformat() if tx_date else None,
                'year': tx_date.year if tx_date else None,
                'amount': float(amount),
                'proceeds_cad': float(proceeds_cad),
                'acb_cad': float(acb_disposed),
                'gain_loss_cad': float(gain_loss),
                'taxable_gain': float(gain_loss * Decimal('0.5')) if gain_loss > 0 else 0,
                'allowable_loss': float(abs(gain_loss) * Decimal('0.5')) if gain_loss < 0 else 0
            })
    
    # Process FT token transactions
    cur.execute('''
        SELECT 
            ft.id,
            ft.tx_hash,
            ft.direction,
            ft.token_symbol,
            ft.token_decimals,
            CAST(ft.amount AS REAL) / POWER(10, COALESCE(ft.token_decimals, 18)) as amount_decimal,
            ft.price_usd,
            ft.value_usd,
            ft.block_timestamp
        FROM ft_transactions ft
        WHERE ft.amount IS NOT NULL AND CAST(ft.amount AS REAL) > 0
        ORDER BY ft.block_timestamp ASC
    ''')
    
    ft_transactions = cur.fetchall()
    
    for tx in ft_transactions:
        token = tx['token_symbol'] or 'UNKNOWN'
        if token not in pools:
            pools[token] = TaxLot(token=token, total_units=Decimal('0'), total_cost_cad=Decimal('0'))
        
        amount = Decimal(str(tx['amount_decimal'] or 0))
        if amount <= 0:
            continue
        
        # Get cost in CAD
        cost_usd = Decimal(str(tx['value_usd'] or 0))
        cost_cad = cost_usd * Decimal('1.35')
        
        timestamp = tx['block_timestamp']
        tx_date = datetime.utcfromtimestamp(timestamp / 1_000_000_000) if timestamp else None
        
        if tx['direction'] == 'in':
            pools[token].add(amount, cost_cad)
        elif tx['direction'] == 'out':
            proceeds_cad = cost_cad
            acb_disposed, _ = pools[token].remove(amount)
            gain_loss = proceeds_cad - acb_disposed
            
            disposals.append({
                'tx_hash': tx['tx_hash'],
                'date': tx_date.isoformat() if tx_date else None,
                'year': tx_date.year if tx_date else None,
                'token': token,
                'amount': float(amount),
                'proceeds_cad': float(proceeds_cad),
                'acb_cad': float(acb_disposed),
                'gain_loss_cad': float(gain_loss),
                'taxable_gain': float(gain_loss * Decimal('0.5')) if gain_loss > 0 else 0,
                'allowable_loss': float(abs(gain_loss) * Decimal('0.5')) if gain_loss < 0 else 0
            })
    
    # Summarize by year
    by_year: Dict[int, Dict] = {}
    for d in disposals:
        yr = d.get('year')
        if not yr:
            continue
        if yr not in by_year:
            by_year[yr] = {
                'total_proceeds': 0,
                'total_acb': 0,
                'total_gain_loss': 0,
                'taxable_gains': 0,
                'allowable_losses': 0,
                'disposal_count': 0
            }
        by_year[yr]['total_proceeds'] += d['proceeds_cad']
        by_year[yr]['total_acb'] += d['acb_cad']
        by_year[yr]['total_gain_loss'] += d['gain_loss_cad']
        by_year[yr]['taxable_gains'] += d['taxable_gain']
        by_year[yr]['allowable_losses'] += d['allowable_loss']
        by_year[yr]['disposal_count'] += 1
    
    # Current pool values
    pool_summary = {
        token: {
            'total_units': float(lot.total_units),
            'total_cost_cad': float(lot.total_cost_cad),
            'acb_per_unit': float(lot.acb_per_unit)
        }
        for token, lot in pools.items()
        if lot.total_units > 0
    }
    
    conn.close()
    
    return {
        'by_year': by_year,
        'pools': pool_summary,
        'total_disposals': len(disposals),
        'disposals': disposals,  # Return all for saving, UI can limit display
        'recent_disposals': disposals[-100:] if len(disposals) > 100 else disposals
    }


def save_acb_to_db(db_path: str = 'neartax.db'):
    """
    Calculate ACB and save disposal records to database
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Create disposals table if not exists
    cur.execute('''
        CREATE TABLE IF NOT EXISTS calculated_disposals (
            id INTEGER PRIMARY KEY,
            tx_id INTEGER,
            tx_hash TEXT,
            token TEXT DEFAULT 'NEAR',
            disposal_date TEXT,
            year INTEGER,
            amount REAL,
            proceeds_cad REAL,
            acb_cad REAL,
            gain_loss_cad REAL,
            taxable_gain REAL,
            allowable_loss REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Calculate
    result = calculate_acb(db_path)
    
    # Clear old calculations
    cur.execute('DELETE FROM calculated_disposals')
    
    # Insert new
    for d in result.get('disposals', []):
        cur.execute('''
            INSERT INTO calculated_disposals 
            (tx_id, tx_hash, token, disposal_date, year, amount, proceeds_cad, acb_cad, gain_loss_cad, taxable_gain, allowable_loss)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            d.get('id'),
            d.get('tx_hash'),
            d.get('token', 'NEAR'),
            d.get('date'),
            d.get('year'),
            d.get('amount'),
            d.get('proceeds_cad'),
            d.get('acb_cad'),
            d.get('gain_loss_cad'),
            d.get('taxable_gain'),
            d.get('allowable_loss')
        ))
    
    conn.commit()
    conn.close()
    
    return result


if __name__ == '__main__':
    import sys
    
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'neartax.db'
    
    print("Calculating ACB and capital gains...")
    result = save_acb_to_db(db_path)
    
    print(f"\nTotal disposals: {result['total_disposals']}")
    
    print("\nCapital Gains by Year:")
    for year, summary in sorted(result['by_year'].items()):
        print(f"\n  {year}:")
        print(f"    Disposals: {summary['disposal_count']}")
        print(f"    Total Proceeds: ${summary['total_proceeds']:,.2f} CAD")
        print(f"    Total ACB: ${summary['total_acb']:,.2f} CAD")
        print(f"    Net Gain/Loss: ${summary['total_gain_loss']:,.2f} CAD")
        print(f"    Taxable Gains (50%): ${summary['taxable_gains']:,.2f} CAD")
        print(f"    Allowable Losses (50%): ${summary['allowable_losses']:,.2f} CAD")
    
    print("\nCurrent Token Pools:")
    for token, pool in result['pools'].items():
        if pool['total_units'] > 0.01:
            print(f"  {token}: {pool['total_units']:,.4f} units @ ${pool['acb_per_unit']:.4f}/unit = ${pool['total_cost_cad']:,.2f} CAD")
