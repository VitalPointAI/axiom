"""Coinbase CSV parser."""

from .base import BaseExchangeParser


class CoinbaseParser(BaseExchangeParser):
    """
    Parser for Coinbase transaction history CSV.
    
    Expected columns:
    Timestamp, Transaction Type, Asset, Quantity Transacted, 
    Spot Price Currency, Spot Price at Transaction, Subtotal, Total, Fees, Notes
    """
    
    exchange_name = "coinbase"
    
    # Map Coinbase transaction types to our standard types
    TYPE_MAP = {
        "Buy": "buy",
        "Sell": "sell",
        "Send": "send",
        "Receive": "receive",
        "Coinbase Earn": "reward",
        "Rewards Income": "staking_reward",
        "Staking Income": "staking_reward",
        "Learning Reward": "reward",
        "Convert": "swap",
    }
    
    def parse_row(self, row):
        # Handle different column name formats
        timestamp = row.get('Timestamp') or row.get('timestamp') or row.get('Date')
        tx_type_raw = row.get('Transaction Type') or row.get('transaction_type') or row.get('Type')
        asset = row.get('Asset') or row.get('asset') or row.get('Currency')
        quantity = row.get('Quantity Transacted') or row.get('quantity_transacted') or row.get('Amount')
        
        if not timestamp or not tx_type_raw:
            return None
        
        tx_type = self.TYPE_MAP.get(tx_type_raw, tx_type_raw.lower())
        
        # Get price/value info
        spot_price = row.get('Spot Price at Transaction') or row.get('spot_price')
        subtotal = row.get('Subtotal') or row.get('subtotal')
        total = row.get('Total') or row.get('total')
        fees = row.get('Fees') or row.get('fees') or row.get('Fee')
        currency = row.get('Spot Price Currency') or row.get('Native Currency') or 'CAD'
        notes = row.get('Notes') or row.get('notes') or ''
        
        return {
            'tx_date': self.parse_datetime(timestamp),
            'tx_type': tx_type,
            'asset': asset,
            'quantity': str(quantity).replace(',', ''),
            'price_per_unit': str(spot_price).replace(',', '') if spot_price else None,
            'total_value': str(total).replace(',', '') if total else None,
            'fee': str(fees).replace(',', '') if fees else None,
            'fee_asset': currency,
            'currency': currency,
            'notes': notes,
        }
