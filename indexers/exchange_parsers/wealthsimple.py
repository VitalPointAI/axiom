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

    def detect(self, filepath: str, first_lines: list) -> bool:
        """Return True if this looks like a Wealthsimple Crypto CSV export."""
        header = " ".join(first_lines[:2]).lower() if first_lines else ""
        # Wealthsimple has Date, Type, Asset, Quantity, Price, Amount, Fee
        # but notably does NOT have USD columns
        has_date = "date" in header
        has_type = "type" in header
        has_asset = "asset" in header
        has_quantity = "quantity" in header
        no_timestamp_utc = "timestamp (utc)" not in header
        no_trade_date = "trade date" not in header
        no_transaction_type = "transaction type" not in header
        return (
            has_date
            and has_type
            and has_asset
            and has_quantity
            and no_timestamp_utc
            and no_trade_date
            and no_transaction_type
        )

    def parse_row(self, row):
        # Handle various column name formats
        timestamp = (
            row.get("Date")
            or row.get("Transaction Date")
            or row.get("date")
        )
        tx_type_raw = (
            row.get("Type")
            or row.get("Transaction Type")
            or row.get("type")
        )
        asset = (
            row.get("Asset")
            or row.get("Symbol")
            or row.get("Currency")
            or row.get("asset")
        )
        quantity = (
            row.get("Quantity")
            or row.get("Amount")
            or row.get("Units")
            or row.get("quantity")
        )

        if not timestamp or not tx_type_raw:
            return None

        tx_type = self.TYPE_MAP.get(tx_type_raw.lower(), tx_type_raw.lower())

        # Get price/value info
        price = row.get("Price") or row.get("price") or row.get("Unit Price")
        total = row.get("Amount") or row.get("Total") or row.get("Value")
        fee = row.get("Fee") or row.get("Fees") or row.get("fee")

        # Wealthsimple sometimes has Amount as total value, not quantity
        if "Units" in row:
            quantity = row.get("Units")
            total = row.get("Amount")

        return {
            "tx_date": self.parse_datetime(timestamp),
            "tx_type": tx_type,
            "asset": asset,
            "quantity": str(quantity).replace(",", "").replace("$", ""),
            "price_per_unit": (
                str(price).replace(",", "").replace("$", "") if price else None
            ),
            "total_value": (
                str(total).replace(",", "").replace("$", "") if total else None
            ),
            "fee": str(fee).replace(",", "").replace("$", "") if fee else None,
            "fee_asset": "CAD",
            "currency": "CAD",  # Wealthsimple is CAD-only
            "notes": "",
            "raw_data": dict(row),
        }
