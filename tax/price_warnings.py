#!/usr/bin/env python3
"""
Price warning system for transactions missing price data.
Surfaces issues that need manual resolution.
"""

from enum import Enum
from dataclasses import dataclass
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class PriceWarningType(Enum):
    """Types of price warnings that need resolution."""
    NO_PRICE_DATA = "no_price_data"          # No price found for this token/date
    UNKNOWN_TOKEN = "unknown_token"           # Token not recognized
    STALE_PRICE = "stale_price"              # Price data >24h from tx time
    ZERO_AMOUNT = "zero_amount"              # Transaction has zero amount
    MANUAL_REQUIRED = "manual_required"       # NFT or other manual valuation needed
    AIRDROP_UNVALUED = "airdrop_unvalued"    # Airdrop needs FMV at receipt
    SPAM_TOKEN = "spam_token"                 # Likely spam/dust token


@dataclass
class PriceWarning:
    """A warning about missing or uncertain price data."""
    warning_type: PriceWarningType
    message: str
    suggested_action: str
    auto_resolvable: bool = False


def add_price_warning_columns():
    """Add price warning columns to transactions table."""
    from db.init import get_connection
    conn = get_connection()

    columns = [
        ("price_warning", "TEXT"),           # Warning type enum
        ("price_warning_msg", "TEXT"),       # Human-readable message
        ("price_manual_usd", "REAL"),        # Manually set price
        ("price_manual_note", "TEXT"),       # Note about manual price
        ("price_resolved", "INTEGER DEFAULT 0"),  # Whether warning resolved
    ]

    for col_name, col_type in columns:
        try:
            conn.execute(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_type}")
            print(f"Added column: {col_name}")
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                print(f"Warning: {e}")

    conn.commit()
    conn.close()


def flag_price_warnings(batch_size: int = 500):
    """
    Scan transactions and flag those with price issues.
    """
    add_price_warning_columns()

    from db.init import get_connection
    conn = get_connection()
    cur = conn.cursor()

    # Get transactions that should have prices but don't
    cur.execute("""
        SELECT id, action_type, method_name, amount, cost_basis_usd,
               NULL as tax_category, block_timestamp
        FROM transactions
        WHERE price_warning IS NULL
        ORDER BY block_timestamp
    """)

    rows = cur.fetchall()
    total = len(rows)
    print(f"Checking {total} transactions for price warnings...")

    warnings_added = 0

    for i, row in enumerate(rows):
        tx_id, action_type, method_name, amount, cost_basis, category, timestamp = row

        warning = None
        msg = None

        # Check if transaction should have a price
        try:
            amt = int(amount) if amount else 0
        except (ValueError, TypeError):
            amt = 0

        near_amount = amt / 1e24

        if near_amount > 0 and cost_basis is None:
            # Has amount but no price
            warning = PriceWarningType.NO_PRICE_DATA.value
            msg = f"Transaction with {near_amount:.4f} NEAR has no price data"

        elif near_amount > 0 and near_amount < 0.0001:
            # Dust amount - might be spam
            warning = PriceWarningType.SPAM_TOKEN.value
            msg = f"Very small amount ({near_amount:.8f} NEAR) - possible spam"

        elif category == "airdrop" and cost_basis is None:
            # Airdrop without valuation
            warning = PriceWarningType.AIRDROP_UNVALUED.value
            msg = "Airdrop needs fair market value at time of receipt"

        elif action_type == "FUNCTION_CALL" and method_name and "nft" in method_name.lower():
            # NFT transaction
            if cost_basis is None:
                warning = PriceWarningType.MANUAL_REQUIRED.value
                msg = f"NFT transaction ({method_name}) needs manual valuation"

        # Update if warning found
        if warning:
            conn.execute("""
                UPDATE transactions
                SET price_warning = ?, price_warning_msg = ?
                WHERE id = ?
            """, (warning, msg, tx_id))
            warnings_added += 1

        if (i + 1) % batch_size == 0:
            conn.commit()
            print(f"  Progress: {i+1}/{total} ({warnings_added} warnings)")

    conn.commit()
    conn.close()

    print(f"Done! Added {warnings_added} price warnings")
    return warnings_added


def get_warnings_summary():
    """Get summary of all price warnings."""
    from db.init import get_connection
    conn = get_connection()

    cur = conn.execute("""
        SELECT price_warning, COUNT(*), SUM(CASE WHEN price_resolved = 1 THEN 1 ELSE 0 END)
        FROM transactions
        WHERE price_warning IS NOT NULL
        GROUP BY price_warning
    """)

    summary = []
    for row in cur.fetchall():
        summary.append({
            "type": row[0],
            "count": row[1],
            "resolved": row[2] or 0,
            "pending": row[1] - (row[2] or 0)
        })

    conn.close()
    return summary


def get_unresolved_warnings(limit: int = 100):
    """Get transactions with unresolved price warnings."""
    from db.init import get_connection
    conn = get_connection()

    cur = conn.execute("""
        SELECT t.id, t.tx_hash, t.block_timestamp, t.action_type, t.method_name,
               t.amount, t.counterparty, t.price_warning, t.price_warning_msg,
               w.account_id
        FROM transactions t
        JOIN wallets w ON t.wallet_id = w.id
        WHERE t.price_warning IS NOT NULL
          AND t.price_resolved = 0
        ORDER BY t.block_timestamp DESC
        LIMIT ?
    """, (limit,))

    warnings = []
    for row in cur.fetchall():
        warnings.append({
            "id": row[0],
            "tx_hash": row[1],
            "timestamp": row[2],
            "action_type": row[3],
            "method_name": row[4],
            "amount": row[5],
            "counterparty": row[6],
            "warning_type": row[7],
            "warning_msg": row[8],
            "wallet": row[9],
        })

    conn.close()
    return warnings


def resolve_warning(tx_id: int, manual_price_usd: float, note: str = None):
    """Manually resolve a price warning."""
    from db.init import get_connection
    conn = get_connection()

    # Get transaction amount
    cur = conn.execute("SELECT amount FROM transactions WHERE id = ?", (tx_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Transaction {tx_id} not found")

    amount = int(row[0]) if row[0] else 0
    near_amount = amount / 1e24

    # Calculate cost basis
    cost_basis = near_amount * manual_price_usd

    conn.execute("""
        UPDATE transactions
        SET price_manual_usd = ?,
            price_manual_note = ?,
            cost_basis_usd = ?,
            price_resolved = 1
        WHERE id = ?
    """, (manual_price_usd, note, cost_basis, tx_id))

    conn.commit()
    conn.close()

    return {"tx_id": tx_id, "cost_basis": cost_basis}


def bulk_resolve_spam(min_amount: float = 0.0001):
    """Mark very small transactions as spam and resolve."""
    from db.init import get_connection
    conn = get_connection()

    # Update transactions already flagged as spam
    cur = conn.execute("""
        UPDATE transactions
        SET cost_basis_usd = 0,
            price_resolved = 1
        WHERE price_warning = 'spam_token'
          AND price_resolved = 0
    """)

    resolved = cur.rowcount
    conn.commit()
    conn.close()

    print(f"Marked {resolved} transactions as spam")
    return resolved


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "--flag":
            flag_price_warnings()
        elif sys.argv[1] == "--summary":
            summary = get_warnings_summary()
            print("\n=== Price Warnings Summary ===")
            for s in summary:
                print(f"  {s['type']}: {s['pending']} pending / {s['count']} total")
        elif sys.argv[1] == "--spam":
            bulk_resolve_spam()
    else:
        print("Usage: python price_warnings.py [--flag|--summary|--spam]")
