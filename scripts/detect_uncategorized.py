#!/usr/bin/env python3
"""
Detect uncategorized transaction patterns that need new rules.

Run after categorization to find patterns that weren't classified.
Outputs patterns that should trigger new rule creation.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path("/home/deploy/neartax/neartax.db")
ALERT_FILE = Path("/home/deploy/neartax/uncategorized_alerts.json")

# Minimum occurrences to trigger an alert (ignore one-off transactions)
MIN_OCCURRENCES = 3
# Minimum NEAR value to consider significant
MIN_NEAR_VALUE = 0.1

def analyze_uncategorized():
    conn = sqlite3.connect(DB_PATH)

    # Find uncategorized patterns by action_type + method_name + counterparty_pattern
    patterns = conn.execute("""
        SELECT
            action_type,
            method_name,
            CASE
                WHEN counterparty LIKE '%.poolv1.near' THEN '*.poolv1.near'
                WHEN counterparty LIKE '%.pool.near' THEN '*.pool.near'
                WHEN counterparty LIKE '%.cdao.near' THEN '*.cdao.near'
                WHEN counterparty LIKE '%.sputnikdao.near' THEN '*.sputnikdao.near'
                WHEN LENGTH(counterparty) = 64 AND counterparty GLOB '[0-9a-f]*' THEN '[implicit_account]'
                WHEN counterparty LIKE '%.lockup.near' THEN '*.lockup.near'
                ELSE counterparty
            END as counterparty_pattern,
            direction,
            COUNT(*) as occurrence_count,
            SUM(CAST(amount AS REAL)/1e24) as total_near,
            MIN(tx_hash) as sample_tx
        FROM transactions
        WHERE tax_category IS NULL
        GROUP BY action_type, method_name, counterparty_pattern, direction
        HAVING occurrence_count >= ? OR total_near >= ?
        ORDER BY total_near DESC, occurrence_count DESC
    """, (MIN_OCCURRENCES, MIN_NEAR_VALUE)).fetchall()

    conn.close()

    return patterns


def format_alert(patterns):
    """Format patterns into actionable alerts."""
    alerts = []

    for p in patterns:
        action_type, method_name, counterparty, direction, count, total_near, sample_tx = p

        # Determine suggested category based on patterns
        suggested_category = suggest_category(action_type, method_name, counterparty, direction)

        alert = {
            "action_type": action_type,
            "method_name": method_name,
            "counterparty_pattern": counterparty,
            "direction": direction,
            "occurrences": count,
            "total_near": round(total_near or 0, 4),
            "sample_tx": sample_tx,
            "suggested_category": suggested_category,
            "needs_rule": True
        }
        alerts.append(alert)

    return alerts


def suggest_category(action_type, method_name, counterparty, direction):
    """Suggest a likely category based on the pattern."""
    method = (method_name or '').lower()
    cp = (counterparty or '').lower()

    # Staking patterns
    if 'pool' in cp or method in ('stake', 'unstake', 'deposit_and_stake', 'withdraw_all'):
        if direction == 'out':
            return 'staking_deposit'
        else:
            return 'unstake_return'

    # DeFi patterns
    if 'ref' in cp or 'swap' in method:
        return 'swap'
    if 'burrow' in cp:
        return 'defi_deposit' if direction == 'out' else 'defi_withdrawal'
    if 'wrap.near' in cp:
        return 'defi_deposit' if direction == 'out' else 'defi_withdrawal'

    # DAO patterns
    if '.cdao.' in cp or 'sputnikdao' in cp:
        return 'dao_operation'

    # NFT patterns
    if 'nft' in method or 'mint' in method:
        return 'nft_operation'

    # Token patterns
    if method.startswith('ft_'):
        return 'token_operation'

    # System
    if counterparty == 'system':
        return 'fee_refund'

    # View/read operations (no value transfer)
    if method.startswith('get_') or method.startswith('is_'):
        return 'non_taxable'

    return 'NEEDS_REVIEW'


def main():
    print("=" * 60)
    print("UNCATEGORIZED TRANSACTION PATTERN DETECTOR")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Min occurrences: {MIN_OCCURRENCES}")
    print(f"Min NEAR value: {MIN_NEAR_VALUE}")
    print()

    patterns = analyze_uncategorized()

    if not patterns:
        print("✅ No significant uncategorized patterns found!")
        return

    alerts = format_alert(patterns)

    # Summary stats
    total_uncategorized = sum(a['occurrences'] for a in alerts)
    total_near = sum(a['total_near'] for a in alerts)

    print(f"⚠️  FOUND {len(alerts)} UNCATEGORIZED PATTERNS")
    print(f"   Total transactions: {total_uncategorized:,}")
    print(f"   Total NEAR: {total_near:,.2f}")
    print()

    # Group by suggested category
    by_category = {}
    for a in alerts:
        cat = a['suggested_category']
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(a)

    for cat, cat_alerts in sorted(by_category.items(), key=lambda x: -sum(a['total_near'] for a in x[1])):
        cat_near = sum(a['total_near'] for a in cat_alerts)
        cat_count = sum(a['occurrences'] for a in cat_alerts)
        print(f"\n--- Suggested: {cat} ({cat_count:,} txs, {cat_near:,.2f} NEAR) ---")

        for a in sorted(cat_alerts, key=lambda x: -x['total_near'])[:10]:
            print(f"  {a['action_type']:<15} {(a['method_name'] or '-'):<25} {a['direction']:<4} "
                  f"{a['occurrences']:>6} txs  {a['total_near']:>12,.2f} NEAR")
            print(f"    counterparty: {a['counterparty_pattern']}")
            print(f"    sample_tx: {a['sample_tx']}")

    # Save to file for programmatic access
    with open(ALERT_FILE, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_patterns': len(alerts),
            'total_transactions': total_uncategorized,
            'total_near': total_near,
            'alerts': alerts
        }, f, indent=2)

    print(f"\n📁 Full alert data saved to: {ALERT_FILE}")
    print("\n🔧 ACTION REQUIRED: Add rules to careful_categorize.py for these patterns")


if __name__ == "__main__":
    main()
