"""Generic CSV parser with auto-detection for Uphold and Coinsquare."""

from .base import BaseExchangeParser


class GenericParser(BaseExchangeParser):
    """
    Generic parser that tries to auto-detect column mappings.

    Works for: Uphold, Coinsquare, and other exchanges with standard formats.
    """

    exchange_name = "generic"

    # Common column name patterns
    DATE_COLUMNS = ["date", "timestamp", "time", "created", "datetime", "trade date"]
    TYPE_COLUMNS = ["type", "transaction type", "kind", "action", "side", "description"]
    ASSET_COLUMNS = ["asset", "currency", "coin", "symbol", "crypto", "token"]
    QUANTITY_COLUMNS = ["quantity", "amount", "units", "size", "volume", "crypto amount"]
    PRICE_COLUMNS = ["price", "rate", "unit price", "spot price", "exchange rate", "market rate"]
    TOTAL_COLUMNS = ["total", "value", "fiat amount", "native amount", "cad", "usd"]
    FEE_COLUMNS = ["fee", "fees", "commission", "spread", "fee amount"]

    # Uphold-specific header columns
    UPHOLD_SIGNATURE_COLUMNS = {"destination currency", "origin currency"}
    # Coinsquare-specific header columns
    COINSQUARE_SIGNATURE_COLUMNS = {"action", "volume"}

    def __init__(self, exchange_name="generic"):
        super().__init__()
        self.exchange_name = exchange_name

    def detect(self, filepath: str, first_lines: list) -> bool:
        """Return True for Uphold or Coinsquare CSV formats."""
        header = " ".join(first_lines[:2]).lower() if first_lines else ""
        header_cols = {col.strip() for col in header.split(",")}

        # Uphold: has "destination currency" and "origin currency"
        if self.UPHOLD_SIGNATURE_COLUMNS.issubset(header_cols):
            return True

        # Coinsquare: has "action" and "volume" columns
        if self.COINSQUARE_SIGNATURE_COLUMNS.issubset(header_cols):
            return True

        return False

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
        tx_type = tx_type_raw.lower() if tx_type_raw else "unknown"

        # Normalize common transaction types
        type_map = {
            "purchase": "buy",
            "bought": "buy",
            "sold": "sell",
            "sale": "sell",
            "transfer in": "receive",
            "transfer out": "send",
            "incoming": "receive",
            "outgoing": "send",
            "reward": "reward",
            "interest": "interest",
            "dividend": "dividend",
        }
        for pattern, mapped in type_map.items():
            if pattern in tx_type:
                tx_type = mapped
                break

        # Find asset — for Uphold, prefer "Destination Currency" for buys
        asset = None
        # Check Uphold-style: Destination Currency is the crypto being bought
        dest_currency = row.get("Destination Currency") or row.get("destination currency")
        origin_currency = row.get("Origin Currency") or row.get("origin currency")
        if dest_currency:
            asset = dest_currency
        else:
            asset = self._find_column(row, self.ASSET_COLUMNS)

        if not asset:
            return None

        # Find quantity — for Uphold, use Destination Amount
        dest_amount = row.get("Destination Amount") or row.get("destination amount")
        if dest_amount:
            quantity = dest_amount
        else:
            quantity = self._find_column(row, self.QUANTITY_COLUMNS)

        if not quantity:
            return None

        # Clean quantity
        quantity = str(quantity).replace(",", "").replace("$", "").strip()
        if quantity.startswith("-"):
            quantity = quantity[1:]  # Remove negative sign

        # Find optional fields
        price = self._find_column(row, self.PRICE_COLUMNS)
        total = self._find_column(row, self.TOTAL_COLUMNS)
        fee_col = row.get("Fee Amount") or row.get("fee amount")
        if not fee_col:
            fee_col = self._find_column(row, self.FEE_COLUMNS)

        # Detect currency from columns or assume CAD
        currency = "CAD"
        for key in row.keys():
            key_lower = key.lower()
            if "usd" in key_lower:
                currency = "USD"
                break
            elif "cad" in key_lower:
                currency = "CAD"
                break
        # For Uphold, use origin currency as the fiat base
        if origin_currency and origin_currency.upper() in ("CAD", "USD"):
            currency = origin_currency.upper()

        return {
            "tx_date": self.parse_datetime(timestamp),
            "tx_type": tx_type,
            "asset": asset.upper() if asset else asset,
            "quantity": quantity,
            "price_per_unit": (
                str(price).replace(",", "").replace("$", "") if price else None
            ),
            "total_value": (
                str(total).replace(",", "").replace("$", "") if total else None
            ),
            "fee": (
                str(fee_col).replace(",", "").replace("$", "") if fee_col else None
            ),
            "currency": currency,
            "notes": "",
            "raw_data": dict(row),
        }


# Convenience aliases for specific exchanges
class UpholdParser(GenericParser):
    def __init__(self):
        super().__init__("uphold")

    def detect(self, filepath: str, first_lines: list) -> bool:
        """Return True for Uphold CSV format."""
        header = " ".join(first_lines[:2]).lower() if first_lines else ""
        header_cols = {col.strip() for col in header.split(",")}
        return self.UPHOLD_SIGNATURE_COLUMNS.issubset(header_cols)


class CoinsquareParser(GenericParser):
    def __init__(self):
        super().__init__("coinsquare")

    def detect(self, filepath: str, first_lines: list) -> bool:
        """Return True for Coinsquare CSV format."""
        header = " ".join(first_lines[:2]).lower() if first_lines else ""
        header_cols = {col.strip() for col in header.split(",")}
        return self.COINSQUARE_SIGNATURE_COLUMNS.issubset(header_cols)
