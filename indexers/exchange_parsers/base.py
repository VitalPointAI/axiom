"""Base class for exchange CSV parsers."""

import csv
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
import sys

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.init import get_connection


class BaseExchangeParser(ABC):
    """Base class for exchange CSV parsers."""
    
    exchange_name = "unknown"
    
    def __init__(self):
        self.transactions = []
        self.errors = []
    
    @abstractmethod
    def parse_row(self, row):
        """
        Parse a single CSV row into standardized format.
        
        Should return dict with:
        - tx_id: exchange's internal ID (optional)
        - tx_date: datetime object
        - tx_type: buy, sell, send, receive, staking_reward, interest, etc
        - asset: BTC, ETH, NEAR, etc
        - quantity: amount (as string to preserve precision)
        - price_per_unit: price in fiat (optional)
        - total_value: total fiat value (optional)
        - fee: fee amount (optional)
        - fee_asset: fee currency (optional)
        - currency: CAD, USD, etc
        - notes: any additional info
        """
        pass
    
    def parse_file(self, filepath):
        """Parse a CSV file."""
        self.transactions = []
        self.errors = []
        
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            # Try to detect delimiter
            sample = f.read(4096)
            f.seek(0)
            
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
            reader = csv.DictReader(f, dialect=dialect)
            
            for i, row in enumerate(reader, 1):
                try:
                    tx = self.parse_row(row)
                    if tx:
                        tx['_row'] = i
                        self.transactions.append(tx)
                except Exception as e:
                    self.errors.append(f"Row {i}: {e}")
        
        return self.transactions
    
    def import_to_db(self, filepath, batch_id=None):
        """Parse file and import to database."""
        batch_id = batch_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        
        transactions = self.parse_file(filepath)
        
        conn = get_connection()
        imported = 0
        
        for tx in transactions:
            try:
                conn.execute("""
                    INSERT INTO exchange_transactions
                    (exchange, tx_id, tx_date, tx_type, asset, quantity,
                     price_per_unit, total_value, fee, fee_asset, currency,
                     notes, import_batch)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.exchange_name,
                    tx.get('tx_id'),
                    tx.get('tx_date'),
                    tx.get('tx_type'),
                    tx.get('asset'),
                    tx.get('quantity'),
                    tx.get('price_per_unit'),
                    tx.get('total_value'),
                    tx.get('fee'),
                    tx.get('fee_asset'),
                    tx.get('currency', 'CAD'),
                    tx.get('notes'),
                    batch_id
                ))
                imported += 1
            except Exception as e:
                self.errors.append(f"DB insert: {e}")
        
        conn.commit()
        conn.close()
        
        return {
            'imported': imported,
            'errors': len(self.errors),
            'batch_id': batch_id
        }
    
    @staticmethod
    def parse_datetime(date_str, formats=None):
        """Try parsing datetime with multiple formats."""
        formats = formats or [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        
        raise ValueError(f"Could not parse date: {date_str}")
