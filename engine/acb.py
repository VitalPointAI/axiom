#!/usr/bin/env python3
"""
Adjusted Cost Base (ACB) Calculator for Canadian Taxes.

Canada uses the "average cost" method for calculating cost basis:
ACB = (Total cost of all units) / (Total number of units owned)

Key rules:
1. Each crypto is tracked separately
2. ACB is pooled across all wallets
3. Fees are added to cost basis on purchase
4. Superficial loss rule: Can't claim loss if you rebuy within 30 days
"""

from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection


class ACBTracker:
    """
    Track Adjusted Cost Base for a single asset.
    
    Implements Canadian average cost method.
    """
    
    def __init__(self, symbol):
        self.symbol = symbol
        self.total_cost = 0.0  # Total cost in CAD
        self.total_units = 0.0  # Total units owned
        self.transactions = []  # History for audit trail
        self.dispositions = []  # Sells/swaps with gain/loss
    
    @property
    def acb_per_unit(self):
        """Current ACB per unit."""
        if self.total_units <= 0:
            return 0
        return self.total_cost / self.total_units
    
    def acquire(self, units, cost_cad, fee_cad=0, date=None, notes=""):
        """
        Record an acquisition (buy, receive, airdrop).
        
        Args:
            units: Number of units acquired
            cost_cad: Cost in CAD (for buys), or FMV (for income)
            fee_cad: Transaction fee in CAD
            date: Transaction date
            notes: Description
        """
        total_cost = cost_cad + fee_cad
        
        self.total_cost += total_cost
        self.total_units += units
        
        self.transactions.append({
            'date': date,
            'type': 'acquire',
            'units': units,
            'cost_cad': total_cost,
            'acb_after': self.acb_per_unit,
            'units_after': self.total_units,
            'notes': notes
        })
    
    def dispose(self, units, proceeds_cad, fee_cad=0, date=None, notes=""):
        """
        Record a disposition (sell, swap, gift).
        
        Args:
            units: Number of units disposed
            proceeds_cad: Proceeds in CAD (sale price * units)
            fee_cad: Transaction fee in CAD
            date: Transaction date
            notes: Description
        
        Returns:
            dict with gain/loss calculation
        """
        if units > self.total_units:
            # Selling more than owned - flag for review
            units = self.total_units
        
        # Calculate gain/loss
        cost_of_units = units * self.acb_per_unit
        net_proceeds = proceeds_cad - fee_cad
        gain_loss = net_proceeds - cost_of_units
        
        # Update totals
        self.total_cost -= cost_of_units
        self.total_units -= units
        
        result = {
            'date': date,
            'type': 'dispose',
            'units': units,
            'proceeds_cad': proceeds_cad,
            'fee_cad': fee_cad,
            'net_proceeds': net_proceeds,
            'acb_used': cost_of_units,
            'gain_loss': gain_loss,
            'is_gain': gain_loss > 0,
            'acb_after': self.acb_per_unit,
            'units_after': self.total_units,
            'notes': notes
        }
        
        self.transactions.append(result)
        self.dispositions.append(result)
        
        return result
    
    def get_summary(self):
        """Get current position summary."""
        total_gains = sum(d['gain_loss'] for d in self.dispositions if d['gain_loss'] > 0)
        total_losses = sum(d['gain_loss'] for d in self.dispositions if d['gain_loss'] < 0)
        
        return {
            'symbol': self.symbol,
            'units_held': self.total_units,
            'total_cost': self.total_cost,
            'acb_per_unit': self.acb_per_unit,
            'total_acquisitions': len([t for t in self.transactions if t['type'] == 'acquire']),
            'total_dispositions': len(self.dispositions),
            'total_gains': total_gains,
            'total_losses': total_losses,
            'net_gain_loss': total_gains + total_losses
        }


class PortfolioACB:
    """Track ACB for entire portfolio (multiple assets)."""
    
    def __init__(self):
        self.assets = {}  # symbol -> ACBTracker
    
    def get_tracker(self, symbol):
        """Get or create tracker for an asset."""
        symbol = symbol.upper()
        if symbol not in self.assets:
            self.assets[symbol] = ACBTracker(symbol)
        return self.assets[symbol]
    
    def acquire(self, symbol, units, cost_cad, fee_cad=0, date=None, notes=""):
        """Record acquisition."""
        tracker = self.get_tracker(symbol)
        tracker.acquire(units, cost_cad, fee_cad, date, notes)
    
    def dispose(self, symbol, units, proceeds_cad, fee_cad=0, date=None, notes=""):
        """Record disposition."""
        tracker = self.get_tracker(symbol)
        return tracker.dispose(units, proceeds_cad, fee_cad, date, notes)
    
    def get_portfolio_summary(self):
        """Get summary of entire portfolio."""
        summaries = []
        total_gains = 0
        total_losses = 0
        
        for symbol, tracker in self.assets.items():
            summary = tracker.get_summary()
            summaries.append(summary)
            total_gains += summary['total_gains']
            total_losses += summary['total_losses']
        
        return {
            'assets': summaries,
            'total_gains': total_gains,
            'total_losses': total_losses,
            'net_gain_loss': total_gains + total_losses,
            'taxable_gain': (total_gains + total_losses) / 2  # 50% inclusion rate
        }
    
    def get_all_dispositions(self, year=None):
        """Get all dispositions, optionally filtered by year."""
        dispositions = []
        
        for symbol, tracker in self.assets.items():
            for d in tracker.dispositions:
                d_copy = d.copy()
                d_copy['symbol'] = symbol
                
                if year and d_copy.get('date'):
                    tx_year = d_copy['date'].year if isinstance(d_copy['date'], datetime) else int(str(d_copy['date'])[:4])
                    if tx_year != year:
                        continue
                
                dispositions.append(d_copy)
        
        # Sort by date
        dispositions.sort(key=lambda x: x.get('date') or datetime.min)
        
        return dispositions


def check_superficial_loss(dispositions, acquisition_dates):
    """
    Check for superficial losses (30-day rule).
    
    Canadian rule: Loss is denied if you buy the same asset within
    30 days before or after the sale.
    
    Returns list of dispositions with superficial loss flags.
    """
    flagged = []
    
    for d in dispositions:
        if d['gain_loss'] >= 0:
            continue  # Not a loss
        
        sale_date = d.get('date')
        if not sale_date:
            continue
        
        if isinstance(sale_date, str):
            sale_date = datetime.strptime(sale_date[:10], "%Y-%m-%d")
        
        # Check for purchases within 30 days
        window_start = sale_date - timedelta(days=30)
        window_end = sale_date + timedelta(days=30)
        
        for acq_date in acquisition_dates:
            if isinstance(acq_date, str):
                acq_date = datetime.strptime(acq_date[:10], "%Y-%m-%d")
            
            if window_start <= acq_date <= window_end:
                flagged.append({
                    **d,
                    'superficial_loss': True,
                    'rebuy_date': acq_date
                })
                break
        else:
            flagged.append({**d, 'superficial_loss': False})
    
    return flagged


if __name__ == "__main__":
    # Example usage
    portfolio = PortfolioACB()
    
    # Simulate some transactions
    portfolio.acquire("NEAR", 1000, 5000, fee_cad=10, 
                     date=datetime(2023, 1, 15), notes="Initial purchase")
    portfolio.acquire("NEAR", 500, 3000, fee_cad=5,
                     date=datetime(2023, 6, 1), notes="Second purchase")
    
    result = portfolio.dispose("NEAR", 300, 2400, fee_cad=8,
                              date=datetime(2023, 12, 1), notes="Partial sale")
    
    print("Disposition Result:")
    print(f"  Units sold: {result['units']}")
    print(f"  Proceeds: ${result['net_proceeds']:.2f}")
    print(f"  ACB used: ${result['acb_used']:.2f}")
    print(f"  Gain/Loss: ${result['gain_loss']:.2f}")
    
    print("\nPortfolio Summary:")
    summary = portfolio.get_portfolio_summary()
    for asset in summary['assets']:
        print(f"\n  {asset['symbol']}:")
        print(f"    Units: {asset['units_held']:.4f}")
        print(f"    ACB/unit: ${asset['acb_per_unit']:.4f}")
        print(f"    Net Gain/Loss: ${asset['net_gain_loss']:.2f}")
    
    print(f"\n  Total Taxable Gain (50%): ${summary['taxable_gain']:.2f}")
