#!/usr/bin/env python3
"""
Cost basis calculator for crypto tax reporting.

Supports:
- ACB (Adjusted Cost Base) - Canadian method
- FIFO (First In, First Out) - US default
- LIFO (Last In, First Out)
- Specific ID

For Canadian taxes:
- Use ACB method (average cost per unit)
- When you sell/dispose: Gain = Proceeds - ACB
- ACB is recalculated after each purchase
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection


def create_cost_basis_tables():
    """Create tables for cost basis tracking."""
    conn = get_connection()
    
    # Holdings table - tracks current holdings and ACB
    conn.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            quantity REAL DEFAULT 0,
            total_cost_usd REAL DEFAULT 0,
            acb_per_unit REAL DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(wallet_id, token),
            FOREIGN KEY (wallet_id) REFERENCES wallets(id)
        )
    """)
    
    # Tax lots - for FIFO/LIFO tracking
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tax_lots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            quantity REAL NOT NULL,
            cost_per_unit REAL NOT NULL,
            total_cost REAL NOT NULL,
            acquired_at INTEGER,
            source TEXT,
            tx_hash TEXT,
            remaining_qty REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id)
        )
    """)
    
    # Disposals - tracks each sale/trade for tax reporting
    conn.execute("""
        CREATE TABLE IF NOT EXISTS disposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            quantity REAL NOT NULL,
            proceeds_usd REAL,
            cost_basis_usd REAL,
            gain_loss_usd REAL,
            disposed_at INTEGER,
            disposal_type TEXT,
            tx_hash TEXT,
            method TEXT DEFAULT 'acb',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id)
        )
    """)
    
    conn.execute("CREATE INDEX IF NOT EXISTS idx_holdings_wallet ON holdings(wallet_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tax_lots_wallet ON tax_lots(wallet_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_disposals_wallet ON disposals(wallet_id)")
    
    conn.commit()
    conn.close()
    print("Cost basis tables created")


class CostBasisCalculator:
    """Calculate cost basis using ACB (Canadian) or FIFO method."""
    
    def __init__(self, wallet_id: int, method: str = "acb"):
        self.wallet_id = wallet_id
        self.method = method  # "acb", "fifo", "lifo"
        self.holdings = defaultdict(lambda: {"qty": Decimal("0"), "cost": Decimal("0")})
        self.tax_lots = defaultdict(list)  # For FIFO/LIFO
        
    def add_acquisition(self, token: str, qty: float, cost_usd: float, 
                       timestamp: int = None, source: str = None, tx_hash: str = None):
        """Record an acquisition (purchase, receive, reward, etc.)."""
        qty = Decimal(str(qty))
        cost = Decimal(str(cost_usd))
        
        # Update holdings (ACB)
        h = self.holdings[token]
        h["qty"] += qty
        h["cost"] += cost
        
        # Add tax lot (for FIFO/LIFO)
        self.tax_lots[token].append({
            "qty": qty,
            "remaining": qty,
            "cost_per_unit": cost / qty if qty > 0 else Decimal("0"),
            "total_cost": cost,
            "timestamp": timestamp,
            "source": source,
            "tx_hash": tx_hash,
        })
        
    def record_disposal(self, token: str, qty: float, proceeds_usd: float,
                       timestamp: int = None, disposal_type: str = "sale", tx_hash: str = None) -> dict:
        """
        Record a disposal (sale, trade, spend) and calculate gain/loss.
        
        Returns dict with gain/loss details.
        """
        qty = Decimal(str(qty))
        proceeds = Decimal(str(proceeds_usd))
        
        h = self.holdings[token]
        
        if h["qty"] <= 0:
            return {
                "error": f"No holdings of {token} to dispose",
                "qty": float(qty),
                "proceeds": float(proceeds),
            }
        
        # Calculate cost basis
        if self.method == "acb":
            # ACB method: average cost per unit
            acb_per_unit = h["cost"] / h["qty"] if h["qty"] > 0 else Decimal("0")
            cost_basis = qty * acb_per_unit
            
            # Update holdings
            h["qty"] -= qty
            h["cost"] -= cost_basis
            
        elif self.method == "fifo":
            # FIFO: use oldest lots first
            cost_basis = self._consume_lots_fifo(token, qty)
            h["qty"] -= qty
            
        elif self.method == "lifo":
            # LIFO: use newest lots first
            cost_basis = self._consume_lots_lifo(token, qty)
            h["qty"] -= qty
        
        else:
            raise ValueError(f"Unknown method: {self.method}")
        
        gain_loss = proceeds - cost_basis
        
        return {
            "token": token,
            "qty": float(qty),
            "proceeds_usd": float(proceeds),
            "cost_basis_usd": float(cost_basis),
            "gain_loss_usd": float(gain_loss),
            "timestamp": timestamp,
            "disposal_type": disposal_type,
            "tx_hash": tx_hash,
            "method": self.method,
        }
    
    def _consume_lots_fifo(self, token: str, qty: Decimal) -> Decimal:
        """Consume tax lots using FIFO method."""
        lots = self.tax_lots[token]
        remaining = qty
        total_cost = Decimal("0")
        
        for lot in lots:
            if remaining <= 0:
                break
            if lot["remaining"] <= 0:
                continue
            
            take = min(remaining, lot["remaining"])
            cost = take * lot["cost_per_unit"]
            
            lot["remaining"] -= take
            remaining -= take
            total_cost += cost
        
        return total_cost
    
    def _consume_lots_lifo(self, token: str, qty: Decimal) -> Decimal:
        """Consume tax lots using LIFO method."""
        lots = self.tax_lots[token]
        remaining = qty
        total_cost = Decimal("0")
        
        for lot in reversed(lots):
            if remaining <= 0:
                break
            if lot["remaining"] <= 0:
                continue
            
            take = min(remaining, lot["remaining"])
            cost = take * lot["cost_per_unit"]
            
            lot["remaining"] -= take
            remaining -= take
            total_cost += cost
        
        return total_cost
    
    def get_acb(self, token: str) -> float:
        """Get current ACB per unit for a token."""
        h = self.holdings[token]
        if h["qty"] <= 0:
            return 0.0
        return float(h["cost"] / h["qty"])
    
    def get_holdings_summary(self) -> dict:
        """Get summary of all holdings."""
        return {
            token: {
                "quantity": float(h["qty"]),
                "total_cost": float(h["cost"]),
                "acb_per_unit": float(h["cost"] / h["qty"]) if h["qty"] > 0 else 0,
            }
            for token, h in self.holdings.items()
            if h["qty"] > 0
        }


def process_transactions_for_cost_basis(wallet_id: int = None, method: str = "acb"):
    """Process all transactions to calculate cost basis."""
    create_cost_basis_tables()
    
    conn = get_connection()
    
    # Get wallets to process
    if wallet_id:
        wallets = [(wallet_id,)]
    else:
        wallets = conn.execute("SELECT id FROM wallets").fetchall()
    
    all_disposals = []
    
    for (wid,) in wallets:
        calc = CostBasisCalculator(wid, method=method)
        
        # Get all transactions in chronological order
        # Include: NEAR transfers, FT transfers, DeFi events
        
        # 1. NEAR transfers with cost basis
        cur = conn.execute("""
            SELECT 'near' as source, direction, amount, cost_basis_usd, 
                   block_timestamp, tx_hash, action_type
            FROM transactions
            WHERE wallet_id = ? AND cost_basis_usd IS NOT NULL
            ORDER BY block_timestamp
        """, (wid,))
        
        for row in cur.fetchall():
            source, direction, amount, cost, ts, tx_hash, action_type = row
            try:
                near_amount = float(amount) / 1e24 if amount else 0
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse NEAR amount %r for tx %s: %s", amount, tx_hash, e)
                continue
            
            if near_amount <= 0:
                continue
            
            if direction == "in":
                calc.add_acquisition("NEAR", near_amount, cost or 0, ts, action_type, tx_hash)
            else:
                disposal = calc.record_disposal("NEAR", near_amount, cost or 0, ts, "transfer", tx_hash)
                if "error" not in disposal:
                    all_disposals.append(disposal)
        
        # 2. FT transfers
        cur = conn.execute("""
            SELECT token_symbol, direction, amount, token_decimals,
                   block_timestamp, tx_hash, price_usd
            FROM ft_transactions
            WHERE wallet_id = ?
            ORDER BY block_timestamp
        """, (wid,))
        
        for row in cur.fetchall():
            token, direction, amount, decimals, ts, tx_hash, price = row
            try:
                decimals = decimals or 18
                token_amount = float(amount) / (10 ** decimals) if amount else 0
            except (ValueError, TypeError, ZeroDivisionError) as e:
                logger.warning("Failed to parse token amount %r for tx %s (token %s): %s", amount, tx_hash, token, e)
                continue
            
            if token_amount <= 0:
                continue
            
            # Estimate value
            if token in ["USDC", "USDT", "DAI", "USN"]:
                value = token_amount  # Stablecoins
            elif price:
                value = token_amount * price
            else:
                value = 0  # Unknown price
            
            if direction == "in":
                calc.add_acquisition(token, token_amount, value, ts, "ft_transfer", tx_hash)
            else:
                disposal = calc.record_disposal(token, token_amount, value, ts, "ft_transfer", tx_hash)
                if "error" not in disposal:
                    all_disposals.append(disposal)
        
        # Save holdings to database
        for token, summary in calc.get_holdings_summary().items():
            conn.execute("""
                INSERT OR REPLACE INTO holdings (wallet_id, token, quantity, total_cost_usd, acb_per_unit)
                VALUES (?, ?, ?, ?, ?)
            """, (wid, token, summary["quantity"], summary["total_cost"], summary["acb_per_unit"]))
    
    # Save disposals
    for d in all_disposals:
        conn.execute("""
            INSERT INTO disposals (wallet_id, token, quantity, proceeds_usd, cost_basis_usd,
                                  gain_loss_usd, disposed_at, disposal_type, tx_hash, method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            wallet_id or 0, d["token"], d["qty"], d["proceeds_usd"], d["cost_basis_usd"],
            d["gain_loss_usd"], d["timestamp"], d["disposal_type"], d["tx_hash"], d["method"]
        ))
    
    conn.commit()
    conn.close()
    
    print(f"Processed {len(all_disposals)} disposals")
    return all_disposals


def get_capital_gains_summary(year: int = None):
    """Get capital gains/losses summary."""
    conn = get_connection()
    
    query = """
        SELECT 
            strftime('%Y', datetime(disposed_at/1000000000, 'unixepoch')) as year,
            token,
            SUM(proceeds_usd) as total_proceeds,
            SUM(cost_basis_usd) as total_cost,
            SUM(gain_loss_usd) as net_gain_loss,
            COUNT(*) as disposals
        FROM disposals
        WHERE disposed_at IS NOT NULL
    """
    
    if year:
        query += f" AND strftime('%Y', datetime(disposed_at/1000000000, 'unixepoch')) = '{year}'"
    
    query += " GROUP BY year, token ORDER BY year, net_gain_loss DESC"
    
    cur = conn.execute(query)
    
    print("\n=== Capital Gains/Losses Summary ===")
    print(f"{'Year':<6} {'Token':<10} {'Proceeds':>12} {'Cost':>12} {'Gain/Loss':>12} {'#':>6}")
    print("-" * 65)
    
    total_gain = 0
    for row in cur.fetchall():
        y, token, proceeds, cost, gain, count = row
        proceeds = proceeds or 0
        cost = cost or 0
        gain = gain or 0
        total_gain += gain
        
        sign = "+" if gain >= 0 else ""
        print(f"{y:<6} {token:<10} ${proceeds:>11,.2f} ${cost:>11,.2f} {sign}${gain:>10,.2f} {count:>6}")
    
    print("-" * 65)
    sign = "+" if total_gain >= 0 else ""
    print(f"{'TOTAL':<6} {'':<10} {'':<12} {'':<12} {sign}${total_gain:>10,.2f}")
    
    conn.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--process":
        process_transactions_for_cost_basis()
    
    get_capital_gains_summary()
