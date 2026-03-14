#!/usr/bin/env python3
"""
Currency conversion for Canadian tax reporting.

Uses Bank of Canada exchange rates (official source) or falls back to 
free APIs for historical USD/CAD rates.

For CRA compliance, use Bank of Canada noon rate on transaction date.
"""

import requests
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection

# Cache for exchange rates
_rate_cache = {}


def create_exchange_rate_table():
    """Create table for caching exchange rates."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exchange_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            from_currency TEXT NOT NULL,
            to_currency TEXT NOT NULL,
            rate REAL NOT NULL,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, from_currency, to_currency)
        )
    """)
    conn.commit()
    conn.close()


def get_bank_of_canada_rate(date_str: str) -> float | None:
    """
    Get USD/CAD rate from Bank of Canada.
    
    Uses the Valet API: https://www.bankofcanada.ca/valet/
    Returns the noon exchange rate.
    """
    try:
        # Bank of Canada API
        url = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json"
        params = {
            "start_date": date_str,
            "end_date": date_str,
        }
        
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        
        observations = data.get("observations", [])
        if observations:
            rate = float(observations[0]["FXUSDCAD"]["v"])
            return rate
        
        return None
    except Exception as e:
        print(f"Bank of Canada API error: {e}")
        return None


def get_exchangerate_api_rate(date_str: str) -> float | None:
    """
    Fallback: Get USD/CAD from exchangerate.host (free, no key required).
    """
    try:
        url = "https://api.exchangerate.host/timeseries"
        params = {
            "start_date": date_str,
            "end_date": date_str,
            "base": "USD",
            "symbols": "CAD",
        }
        
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        
        if data.get("success") and date_str in data.get("rates", {}):
            return data["rates"][date_str]["CAD"]
        
        return None
    except Exception as e:
        print(f"ExchangeRate API error: {e}")
        return None


def get_usd_cad_rate(timestamp_ns: int = None, date_str: str = None) -> float:
    """
    Get USD to CAD exchange rate for a given date.
    
    Args:
        timestamp_ns: Nanosecond timestamp (NEAR blockchain format)
        date_str: Date string in YYYY-MM-DD format
    
    Returns:
        Exchange rate (1 USD = X CAD)
    """
    # Convert timestamp to date
    if timestamp_ns:
        ts_sec = timestamp_ns // 1_000_000_000 if timestamp_ns > 1e12 else timestamp_ns
        dt = datetime.fromtimestamp(ts_sec)
        date_str = dt.strftime("%Y-%m-%d")
    
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    # Check cache
    cache_key = f"USD_CAD_{date_str}"
    if cache_key in _rate_cache:
        return _rate_cache[cache_key]
    
    # Check database
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT rate FROM exchange_rates WHERE date = ? AND from_currency = 'USD' AND to_currency = 'CAD'",
            (date_str,)
        )
        row = cur.fetchone()
        if row:
            _rate_cache[cache_key] = row[0]
            conn.close()
            return row[0]
    except Exception:
        pass
    
    # Fetch from Bank of Canada (preferred)
    rate = get_bank_of_canada_rate(date_str)
    source = "bank_of_canada"
    
    # Fallback to exchangerate.host
    if rate is None:
        rate = get_exchangerate_api_rate(date_str)
        source = "exchangerate_host"
    
    # Final fallback - use approximate rate
    if rate is None:
        rate = 1.35  # Approximate USD/CAD
        source = "fallback"
    
    # Cache in database
    try:
        create_exchange_rate_table()
        conn.execute(
            "INSERT OR REPLACE INTO exchange_rates (date, from_currency, to_currency, rate, source) VALUES (?, ?, ?, ?, ?)",
            (date_str, "USD", "CAD", rate, source)
        )
        conn.commit()
    except Exception:
        pass
    
    conn.close()
    
    _rate_cache[cache_key] = rate
    return rate


def usd_to_cad(usd_amount: float, timestamp_ns: int = None, date_str: str = None) -> float:
    """Convert USD to CAD at historical rate."""
    if usd_amount is None or usd_amount == 0:
        return 0.0
    
    rate = get_usd_cad_rate(timestamp_ns, date_str)
    return usd_amount * rate


def add_cad_columns():
    """Add CAD columns to relevant tables."""
    conn = get_connection()
    
    tables_columns = [
        ("transactions", "cost_basis_cad"),
        ("ft_transactions", "value_cad"),
        ("defi_events", "value_cad"),
        ("staking_rewards", "value_cad"),
        ("disposals", "proceeds_cad"),
        ("disposals", "cost_basis_cad"),
        ("disposals", "gain_loss_cad"),
    ]
    
    for table, column in tables_columns:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} REAL")
            print(f"Added {column} to {table}")
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                print(f"Warning: {e}")
    
    conn.commit()
    conn.close()


def backfill_cad_values(batch_size: int = 500):
    """Backfill CAD values for all transactions."""
    add_cad_columns()
    create_exchange_rate_table()
    
    conn = get_connection()
    
    # 1. Transactions
    print("Backfilling transactions...")
    cur = conn.execute("""
        SELECT id, block_timestamp, cost_basis_usd 
        FROM transactions 
        WHERE cost_basis_usd IS NOT NULL AND cost_basis_cad IS NULL
    """)
    rows = cur.fetchall()
    
    for i, (tx_id, ts, usd) in enumerate(rows):
        cad = usd_to_cad(usd, ts)
        conn.execute("UPDATE transactions SET cost_basis_cad = ? WHERE id = ?", (cad, tx_id))
        if (i + 1) % batch_size == 0:
            conn.commit()
            print(f"  Transactions: {i+1}/{len(rows)}")
    conn.commit()
    
    # 2. FT Transactions
    print("Backfilling FT transactions...")
    cur = conn.execute("""
        SELECT id, block_timestamp, price_usd, amount, token_decimals
        FROM ft_transactions 
        WHERE value_cad IS NULL AND price_usd IS NOT NULL
    """)
    rows = cur.fetchall()
    
    for i, (tx_id, ts, price, amount, decimals) in enumerate(rows):
        try:
            decimals = decimals or 18
            value_usd = float(amount) / (10 ** decimals) * price if amount and price else 0
            cad = usd_to_cad(value_usd, ts)
            conn.execute("UPDATE ft_transactions SET value_cad = ? WHERE id = ?", (cad, tx_id))
        except Exception:
            pass
        if (i + 1) % batch_size == 0:
            conn.commit()
            print(f"  FT Transactions: {i+1}/{len(rows)}")
    conn.commit()
    
    # 3. DeFi Events
    print("Backfilling DeFi events...")
    cur = conn.execute("""
        SELECT id, block_timestamp, value_usd 
        FROM defi_events 
        WHERE value_usd IS NOT NULL AND value_cad IS NULL
    """)
    rows = cur.fetchall()
    
    for i, (tx_id, ts, usd) in enumerate(rows):
        cad = usd_to_cad(usd, ts)
        conn.execute("UPDATE defi_events SET value_cad = ? WHERE id = ?", (cad, tx_id))
        if (i + 1) % batch_size == 0:
            conn.commit()
    conn.commit()
    
    # 4. Staking Rewards
    print("Backfilling staking rewards...")
    cur = conn.execute("""
        SELECT id, block_timestamp, value_usd 
        FROM staking_rewards 
        WHERE value_usd IS NOT NULL AND value_cad IS NULL
    """)
    rows = cur.fetchall()
    
    for i, (tx_id, ts, usd) in enumerate(rows):
        cad = usd_to_cad(usd, ts)
        conn.execute("UPDATE staking_rewards SET value_cad = ? WHERE id = ?", (cad, tx_id))
    conn.commit()
    
    # 5. Disposals
    print("Backfilling disposals...")
    cur = conn.execute("""
        SELECT id, disposed_at, proceeds_usd, cost_basis_usd, gain_loss_usd 
        FROM disposals 
        WHERE proceeds_cad IS NULL
    """)
    rows = cur.fetchall()
    
    for i, (tx_id, ts, proceeds, cost, gain) in enumerate(rows):
        proceeds_cad = usd_to_cad(proceeds, ts) if proceeds else 0
        cost_cad = usd_to_cad(cost, ts) if cost else 0
        gain_cad = usd_to_cad(gain, ts) if gain else 0
        conn.execute(
            "UPDATE disposals SET proceeds_cad = ?, cost_basis_cad = ?, gain_loss_cad = ? WHERE id = ?",
            (proceeds_cad, cost_cad, gain_cad, tx_id)
        )
        if (i + 1) % batch_size == 0:
            conn.commit()
    conn.commit()
    
    conn.close()
    print("CAD backfill complete!")


def get_yearly_exchange_rates(year: int) -> dict:
    """Get average and year-end exchange rates for a year."""
    # Year-end rate
    year_end = f"{year}-12-31"
    year_end_rate = get_usd_cad_rate(date_str=year_end)
    
    # Get average (sample monthly)
    rates = []
    for month in range(1, 13):
        date_str = f"{year}-{month:02d}-15"
        try:
            rate = get_usd_cad_rate(date_str=date_str)
            rates.append(rate)
        except Exception:
            pass
    
    avg_rate = sum(rates) / len(rates) if rates else year_end_rate
    
    return {
        "year": year,
        "year_end_rate": year_end_rate,
        "average_rate": avg_rate,
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--backfill":
        backfill_cad_values()
    else:
        # Test current rate
        rate = get_usd_cad_rate()
        print(f"Current USD/CAD rate: {rate:.4f}")
        print(f"$100 USD = ${100 * rate:.2f} CAD")
        
        # Test historical
        rate_2023 = get_usd_cad_rate(date_str="2023-12-31")
        print(f"2023-12-31 USD/CAD rate: {rate_2023:.4f}")
