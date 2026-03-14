#!/usr/bin/env python3
"""
Tax report generator for NearTax.

Generates:
- Capital gains/losses report by tax year
- Income report (staking rewards, DeFi rewards)
- Year-end inventory snapshot (holdings as of Dec 31)
- T1135 foreign property report (Canada)

Supports filtering by:
- Date range (fiscal year)
- Token
- Transaction type
- Protocol
"""

import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection


class TaxReportGenerator:
    """Generate tax reports for a given fiscal year."""
    
    def __init__(self, year: int, fiscal_start_month: int = 1, fiscal_start_day: int = 1):
        """
        Initialize report generator.
        
        Args:
            year: Tax year (e.g., 2024)
            fiscal_start_month: Month fiscal year starts (default January = 1)
            fiscal_start_day: Day fiscal year starts (default 1)
        """
        self.year = year
        
        # Calculate fiscal year boundaries
        self.start_date = datetime(year, fiscal_start_month, fiscal_start_day)
        if fiscal_start_month == 1 and fiscal_start_day == 1:
            self.end_date = datetime(year, 12, 31, 23, 59, 59)
        else:
            # Fiscal year ends day before start of next year
            self.end_date = datetime(year + 1, fiscal_start_month, fiscal_start_day) - timedelta(seconds=1)
        
        # Convert to nanosecond timestamps (NEAR format)
        self.start_ts = int(self.start_date.timestamp()) * 1_000_000_000
        self.end_ts = int(self.end_date.timestamp()) * 1_000_000_000
    
    def get_capital_gains_report(self, token: str = None, min_value: float = 0) -> dict:
        """
        Generate capital gains/losses report.
        
        Args:
            token: Filter by specific token (optional)
            min_value: Minimum absolute value to include (filter dust)
        """
        conn = get_connection()
        
        query = """
            SELECT token, quantity, proceeds_usd, cost_basis_usd, gain_loss_usd,
                   disposed_at, disposal_type, tx_hash
            FROM disposals
            WHERE disposed_at >= ? AND disposed_at <= ?
        """
        params = [self.start_ts, self.end_ts]
        
        if token:
            query += " AND token = ?"
            params.append(token)
        
        query += " ORDER BY disposed_at"
        
        cur = conn.execute(query, params)
        
        disposals = []
        totals = {
            "total_proceeds": 0,
            "total_cost": 0,
            "total_gain": 0,
            "total_loss": 0,
            "net_gain_loss": 0,
        }
        
        for row in cur.fetchall():
            token, qty, proceeds, cost, gain, ts, dtype, tx = row
            
            proceeds = proceeds or 0
            cost = cost or 0
            gain = gain or 0
            
            if abs(gain) < min_value:
                continue
            
            disposals.append({
                "token": token,
                "quantity": qty,
                "proceeds_usd": proceeds,
                "cost_basis_usd": cost,
                "gain_loss_usd": gain,
                "date": datetime.fromtimestamp(ts / 1_000_000_000).strftime("%Y-%m-%d") if ts else None,
                "type": dtype,
                "tx_hash": tx,
            })
            
            totals["total_proceeds"] += proceeds
            totals["total_cost"] += cost
            if gain >= 0:
                totals["total_gain"] += gain
            else:
                totals["total_loss"] += abs(gain)
            totals["net_gain_loss"] += gain
        
        conn.close()
        
        return {
            "year": self.year,
            "period": f"{self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}",
            "disposals": disposals,
            "summary": totals,
        }
    
    def get_income_report(self) -> dict:
        """Generate income report (staking rewards, DeFi rewards, etc.)."""
        conn = get_connection()
        
        income_items = []
        
        # 1. Staking rewards
        cur = conn.execute("""
            SELECT validator, reward_near, value_usd, block_timestamp, notes
            FROM staking_rewards
            WHERE block_timestamp >= ? AND block_timestamp <= ?
        """, (self.start_ts, self.end_ts))
        
        for row in cur.fetchall():
            validator, near, usd, ts, notes = row
            income_items.append({
                "type": "staking_reward",
                "source": validator,
                "amount": near,
                "token": "NEAR",
                "value_usd": usd or 0,
                "date": datetime.fromtimestamp(ts / 1_000_000_000).strftime("%Y-%m-%d") if ts else None,
                "notes": notes,
            })
        
        # 2. DeFi income (rewards)
        cur = conn.execute("""
            SELECT protocol, event_type, token_symbol, amount_decimal, value_usd, 
                   block_timestamp, tax_notes
            FROM defi_events
            WHERE tax_category = 'income'
            AND block_timestamp >= ? AND block_timestamp <= ?
        """, (self.start_ts, self.end_ts))
        
        for row in cur.fetchall():
            protocol, etype, token, amount, usd, ts, notes = row
            income_items.append({
                "type": f"defi_{etype}",
                "source": protocol,
                "amount": amount,
                "token": token,
                "value_usd": usd or 0,
                "date": datetime.fromtimestamp(ts / 1_000_000_000).strftime("%Y-%m-%d") if ts else None,
                "notes": notes,
            })
        
        conn.close()
        
        # Calculate totals by type
        totals = {}
        for item in income_items:
            t = item["type"]
            if t not in totals:
                totals[t] = {"count": 0, "total_usd": 0}
            totals[t]["count"] += 1
            totals[t]["total_usd"] += item["value_usd"]
        
        total_income = sum(t["total_usd"] for t in totals.values())
        
        return {
            "year": self.year,
            "period": f"{self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}",
            "items": income_items,
            "by_type": totals,
            "total_income_usd": total_income,
        }
    
    def get_year_end_inventory(self, as_of_date: datetime = None) -> dict:
        """
        Generate inventory of token holdings as of year end (Dec 31).
        
        For T1135 reporting and year-end balance tracking.
        """
        if as_of_date is None:
            as_of_date = self.end_date
        
        as_of_ts = int(as_of_date.timestamp()) * 1_000_000_000
        
        conn = get_connection()
        
        # Calculate holdings as of the given date
        # This requires replaying transactions up to that date
        
        holdings = {}
        
        # 1. Process NEAR transfers
        cur = conn.execute("""
            SELECT direction, amount, cost_basis_usd
            FROM transactions
            WHERE block_timestamp <= ?
            AND amount IS NOT NULL
        """, (as_of_ts,))
        
        near_qty = 0
        near_cost = 0
        for row in cur.fetchall():
            direction, amount, cost = row
            try:
                amt = float(amount) / 1e24
            except Exception:
                continue
            
            if direction == "in":
                near_qty += amt
                near_cost += cost or 0
            else:
                near_qty -= amt
                near_cost -= cost or 0
        
        if near_qty > 0:
            holdings["NEAR"] = {
                "quantity": near_qty,
                "cost_basis_usd": max(0, near_cost),
                "acb_per_unit": near_cost / near_qty if near_qty > 0 else 0,
            }
        
        # 2. Process FT transfers
        cur = conn.execute("""
            SELECT token_symbol, direction, amount, token_decimals, price_usd
            FROM ft_transactions
            WHERE block_timestamp <= ?
        """, (as_of_ts,))
        
        ft_holdings = {}
        for row in cur.fetchall():
            token, direction, amount, decimals, price = row
            try:
                decimals = decimals or 18
                amt = float(amount) / (10 ** decimals)
            except Exception:
                continue
            
            if token not in ft_holdings:
                ft_holdings[token] = {"qty": 0, "cost": 0}
            
            value = amt * price if price else 0
            
            if direction == "in":
                ft_holdings[token]["qty"] += amt
                ft_holdings[token]["cost"] += value
            else:
                ft_holdings[token]["qty"] -= amt
                ft_holdings[token]["cost"] -= value
        
        for token, data in ft_holdings.items():
            if data["qty"] > 0.01:  # Filter dust
                holdings[token] = {
                    "quantity": data["qty"],
                    "cost_basis_usd": max(0, data["cost"]),
                    "acb_per_unit": data["cost"] / data["qty"] if data["qty"] > 0 else 0,
                }
        
        conn.close()
        
        # Sort by value
        holdings_list = [
            {"token": k, **v} for k, v in holdings.items()
        ]
        holdings_list.sort(key=lambda x: x["cost_basis_usd"], reverse=True)
        
        total_cost = sum(h["cost_basis_usd"] for h in holdings_list)
        
        return {
            "as_of": as_of_date.strftime("%Y-%m-%d"),
            "year": self.year,
            "holdings": holdings_list,
            "total_cost_basis_usd": total_cost,
            "holdings_count": len(holdings_list),
        }
    
    def generate_full_report(self) -> dict:
        """Generate complete tax report for the year."""
        return {
            "tax_year": self.year,
            "fiscal_period": {
                "start": self.start_date.strftime("%Y-%m-%d"),
                "end": self.end_date.strftime("%Y-%m-%d"),
            },
            "capital_gains": self.get_capital_gains_report(),
            "income": self.get_income_report(),
            "year_end_inventory": self.get_year_end_inventory(),
            "generated_at": datetime.now().isoformat(),
        }


def generate_t1135_report(year: int, threshold_cad: float = 100000) -> dict:
    """
    Generate T1135 Foreign Income Verification Statement data.
    
    Required in Canada if cost of foreign property exceeds $100,000 CAD.
    Crypto is considered specified foreign property.
    """
    gen = TaxReportGenerator(year)
    inventory = gen.get_year_end_inventory()
    
    # For T1135, we need max cost during year and year-end cost
    # This is simplified - just using year-end for now
    
    report = {
        "form": "T1135",
        "year": year,
        "category": "Category 7 - Cryptocurrencies",
        "description": "Digital currencies held on NEAR Protocol blockchain",
        "country": "N/A (Decentralized)",
        "max_cost_during_year_cad": inventory["total_cost_basis_usd"] * 1.35,  # Rough USD to CAD
        "cost_at_year_end_cad": inventory["total_cost_basis_usd"] * 1.35,
        "income_cad": 0,  # Need to calculate
        "gain_loss_cad": 0,  # Need to calculate
        "holdings": inventory["holdings"][:10],  # Top 10
        "note": "This is estimated data - verify with official records",
    }
    
    return report


def print_tax_report(year: int):
    """Print formatted tax report for a year."""
    
    gen = TaxReportGenerator(year)
    
    print("=" * 70)
    print(f"NEARTAX - TAX REPORT FOR {year}")
    print(f"Period: {gen.start_date.strftime('%Y-%m-%d')} to {gen.end_date.strftime('%Y-%m-%d')}")
    print("=" * 70)
    
    # Capital Gains
    cg = gen.get_capital_gains_report(min_value=1.0)
    print("\n📈 CAPITAL GAINS/LOSSES")
    print("-" * 50)
    print(f"  Total Proceeds:    ${cg['summary']['total_proceeds']:>15,.2f}")
    print(f"  Total Cost Basis:  ${cg['summary']['total_cost']:>15,.2f}")
    print(f"  Total Gains:       ${cg['summary']['total_gain']:>15,.2f}")
    print(f"  Total Losses:      ${cg['summary']['total_loss']:>15,.2f}")
    print(f"  NET GAIN/LOSS:     ${cg['summary']['net_gain_loss']:>15,.2f}")
    print(f"  Disposals: {len(cg['disposals'])}")
    
    # Income
    income = gen.get_income_report()
    print("\n💰 INCOME (Taxable)")
    print("-" * 50)
    for itype, data in income["by_type"].items():
        print(f"  {itype}: ${data['total_usd']:,.2f} ({data['count']} events)")
    print(f"  TOTAL INCOME:      ${income['total_income_usd']:>15,.2f}")
    
    # Year-end inventory
    inv = gen.get_year_end_inventory()
    print(f"\n📦 YEAR-END INVENTORY (as of {inv['as_of']})")
    print("-" * 50)
    print(f"  {'Token':<15} {'Quantity':>15} {'Cost Basis':>15}")
    for h in inv["holdings"][:15]:
        print(f"  {h['token']:<15} {h['quantity']:>15,.2f} ${h['cost_basis_usd']:>14,.2f}")
    print(f"\n  Total Holdings: {inv['holdings_count']}")
    print(f"  Total Cost Basis: ${inv['total_cost_basis_usd']:,.2f}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    import sys
    from datetime import timedelta
    
    if len(sys.argv) > 1:
        year = int(sys.argv[1])
    else:
        year = 2024  # Default to last complete year
    
    print_tax_report(year)
