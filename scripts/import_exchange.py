#!/usr/bin/env python3
"""Import exchange CSV files into the database."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import init_db, get_connection
from indexers.exchange_parsers import get_parser, list_supported


def list_imports():
    """List previous imports."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT exchange, import_batch, COUNT(*) as txs, 
               MIN(tx_date) as first_date, MAX(tx_date) as last_date
        FROM exchange_transactions
        GROUP BY exchange, import_batch
        ORDER BY import_batch DESC
    """).fetchall()
    conn.close()
    
    if not rows:
        print("No imports found.")
        return
    
    print("\nPrevious Imports:")
    print("-" * 80)
    for row in rows:
        print(f"  {row[0]:15} | Batch: {row[1]} | {row[2]:5} txs | {row[3]} to {row[4]}")
    print("-" * 80)


def import_csv(filepath, exchange=None, dry_run=False):
    """Import a CSV file."""
    filepath = Path(filepath)
    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        return
    
    # Auto-detect exchange from filename if not specified
    if not exchange:
        filename = filepath.stem.lower()
        for ex in list_supported():
            if ex in filename:
                exchange = ex
                break
        if not exchange:
            exchange = "generic"
    
    print(f"\nImporting: {filepath}")
    print(f"Exchange: {exchange}")
    print(f"Dry run: {dry_run}")
    
    # Get parser
    parser_class = get_parser(exchange)
    parser = parser_class()
    
    # Parse file
    transactions = parser.parse_file(filepath)
    
    print(f"\nParsed {len(transactions)} transactions")
    
    if parser.errors:
        print(f"Errors: {len(parser.errors)}")
        for err in parser.errors[:5]:
            print(f"  - {err}")
        if len(parser.errors) > 5:
            print(f"  ... and {len(parser.errors) - 5} more")
    
    if transactions:
        # Show sample
        print("\nSample transactions:")
        for tx in transactions[:3]:
            print(f"  {tx['tx_date']} | {tx['tx_type']:10} | {tx['quantity']} {tx['asset']}")
    
    if dry_run:
        print("\nDry run - no data imported.")
        return
    
    # Import to database
    result = parser.import_to_db(filepath)
    
    print("\nImport complete:")
    print(f"  Imported: {result['imported']}")
    print(f"  Errors: {result['errors']}")
    print(f"  Batch ID: {result['batch_id']}")


def main():
    parser = argparse.ArgumentParser(
        description="Import exchange CSV files"
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="CSV file to import"
    )
    parser.add_argument(
        "--exchange", "-e",
        help="Exchange name (coinbase, crypto_com, wealthsimple, etc)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Parse only, don't import"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List previous imports"
    )
    parser.add_argument(
        "--supported", "-s",
        action="store_true",
        help="List supported exchanges"
    )
    
    args = parser.parse_args()
    
    # Initialize database
    init_db()
    
    if args.supported:
        print("\nSupported exchanges:")
        for ex in list_supported():
            print(f"  - {ex}")
        return
    
    if args.list:
        list_imports()
        return
    
    if not args.file:
        parser.print_help()
        return
    
    import_csv(args.file, args.exchange, args.dry_run)


if __name__ == "__main__":
    main()
