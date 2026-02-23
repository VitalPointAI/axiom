"""Wealthsimple Crypto CSV parser."""

from .base import BaseExchangeParser


class WealthsimpleParser(BaseExchangeParser):
    """
    Parser for Wealthsimple Crypto transaction history CSV.
    
    Expected columns:
    Date, Type, Asset, Quantity, Price, Amount, Fee
    
    Note: Wealthsimple is CAD-only.
    """
    
    exchange_name = "wealthsimple"
    
    TYPE_MAP = {
        "buy": "buy",
        "sell": "sell",
        "deposit": "receive",
        "withdrawal": "send",
        "interest": "interest",
        "staking": "staking_reward",
    }
    
    def parse_row(self, row):
        # Handle various column name formats
        timestamp = (
            row.get('Date') or 
            row.get('Transaction Date') or 
            row.get('date')
        )
        tx_type_raw = (
            row.get('Type') or 
            row.get('Transaction Type') or 
            row.get('type')
        )
        asset = (
            row.get('Asset') or 
            row.get('Symbol') or 
            row.get('Currency') or
            row.get('asset')
        )
        quantity = (
            row.get('Quantity') or 
            row.get('Amount') or 
            row.get('Units') or
            row.get('quantity')
        )
        
        if not timestamp or not tx_type_raw:
            return None
        
        tx_type = self.TYPE_MAP.get(tx_type_raw.lower(), tx_type_raw.lower())
        
        # Get price/value info
        price = row.get('Price') or row.get('price') or row.get('Unit Price')
        total = row.get('Amount') or row.get('Total') or row.get('Value')
        fee = row.get('Fee') or row.get('Fees') or row.get('fee')
        
        # Wealthsimple sometimes has Amount as total value, not quantity
        # Check if we need to swap
        if 'Units' in row:
            quantity = row.get('Units')
            total = row.get('Amount')
        
        return {
            'tx_date': self.parse_datetime(timestamp),
            'tx_type': tx_type,
            'asset': asset,
            'quantity': str(quantity).replace(',', '').replace('$', ''),
            'price_per_unit': str(price).replace(',', '').replace('$', '') if price else None,
            'total_value': str(total).replace(',', '').replace('$', '') if total else None,
            'fee': str(fee).replace(',', '').replace('$', '') if fee else None,
            'fee_asset': 'CAD',
            'currency': 'CAD',  # Wealthsimple is CAD-only
            'notes': '',
        }
