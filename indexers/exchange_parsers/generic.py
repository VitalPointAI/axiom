"""Generic CSV parser with auto-detection."""

from .base import BaseExchangeParser


class GenericParser(BaseExchangeParser):
    """
    Generic parser that tries to auto-detect column mappings.
    
    Works for: Uphold, Coinsquare, and other exchanges with standard formats.
    """
    
    exchange_name = "generic"
    
    # Common column name patterns
    DATE_COLUMNS = ['date', 'timestamp', 'time', 'created', 'datetime', 'trade date']
    TYPE_COLUMNS = ['type', 'transaction type', 'kind', 'action', 'side', 'description']
    ASSET_COLUMNS = ['asset', 'currency', 'coin', 'symbol', 'crypto', 'token']
    QUANTITY_COLUMNS = ['quantity', 'amount', 'units', 'size', 'volume', 'crypto amount']
    PRICE_COLUMNS = ['price', 'rate', 'unit price', 'spot price', 'exchange rate']
    TOTAL_COLUMNS = ['total', 'value', 'fiat amount', 'native amount', 'cad', 'usd']
    FEE_COLUMNS = ['fee', 'fees', 'commission', 'spread']
    
    def __init__(self, exchange_name="generic"):
        super().__init__()
        self.exchange_name = exchange_name
    
    def _find_column(self, row, patterns):
        """Find a column matching any of the patterns."""
        for key in row.keys():
            key_lower = key.lower().strip()
            for pattern in patterns:
                if pattern in key_lower or key_lower in pattern:
                    if row[key]:  # Only return if has value
                        return row[key]
        return None
    
    def parse_row(self, row):
        # Find date
        timestamp = self._find_column(row, self.DATE_COLUMNS)
        if not timestamp:
            return None
        
        # Find transaction type
        tx_type_raw = self._find_column(row, self.TYPE_COLUMNS)
        tx_type = tx_type_raw.lower() if tx_type_raw else 'unknown'
        
        # Normalize common transaction types
        type_map = {
            'purchase': 'buy',
            'bought': 'buy',
            'sold': 'sell',
            'sale': 'sell',
            'transfer in': 'receive',
            'transfer out': 'send',
            'incoming': 'receive',
            'outgoing': 'send',
            'reward': 'reward',
            'interest': 'interest',
            'dividend': 'dividend',
        }
        for pattern, mapped in type_map.items():
            if pattern in tx_type:
                tx_type = mapped
                break
        
        # Find asset
        asset = self._find_column(row, self.ASSET_COLUMNS)
        if not asset:
            return None
        
        # Find quantity
        quantity = self._find_column(row, self.QUANTITY_COLUMNS)
        if not quantity:
            return None
        
        # Clean quantity
        quantity = str(quantity).replace(',', '').replace('$', '').strip()
        if quantity.startswith('-'):
            quantity = quantity[1:]  # Remove negative sign
        
        # Find optional fields
        price = self._find_column(row, self.PRICE_COLUMNS)
        total = self._find_column(row, self.TOTAL_COLUMNS)
        fee = self._find_column(row, self.FEE_COLUMNS)
        
        # Detect currency from columns or assume CAD
        currency = 'CAD'
        for key in row.keys():
            key_lower = key.lower()
            if 'usd' in key_lower:
                currency = 'USD'
                break
            elif 'cad' in key_lower:
                currency = 'CAD'
                break
        
        return {
            'tx_date': self.parse_datetime(timestamp),
            'tx_type': tx_type,
            'asset': asset.upper(),
            'quantity': quantity,
            'price_per_unit': str(price).replace(',', '').replace('$', '') if price else None,
            'total_value': str(total).replace(',', '').replace('$', '') if total else None,
            'fee': str(fee).replace(',', '').replace('$', '') if fee else None,
            'currency': currency,
            'notes': '',
        }


# Convenience aliases for specific exchanges
class UpholdParser(GenericParser):
    def __init__(self):
        super().__init__("uphold")


class CoinsquareParser(GenericParser):
    def __init__(self):
        super().__init__("coinsquare")
