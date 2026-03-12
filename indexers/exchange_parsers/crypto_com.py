"""Crypto.com CSV parser (Exchange and App)."""

from .base import BaseExchangeParser


class CryptoComParser(BaseExchangeParser):
    """
    Parser for Crypto.com transaction history CSV.

    Handles both Crypto.com Exchange and Crypto.com App exports.

    Expected columns (App):
    Timestamp (UTC), Transaction Description, Currency, Amount,
    To Currency, To Amount, Native Currency, Native Amount,
    Native Amount (in USD), Transaction Kind

    Expected columns (Exchange):
    Trade Date, Pair, Side, Price, Executed, Fee, Total
    """

    exchange_name = "crypto_com"

    TYPE_MAP = {
        "crypto_purchase": "buy",
        "crypto_withdrawal": "send",
        "crypto_deposit": "receive",
        "crypto_exchange": "swap",
        "viban_purchase": "buy",
        "card_cashback": "reward",
        "referral_bonus": "reward",
        "staking_reward": "staking_reward",
        "crypto_earn_interest_paid": "interest",
        "crypto_earn_deposit": "deposit",
        "crypto_earn_withdrawal": "withdrawal",
        "supercharger_reward": "reward",
        "rewards_platform_deposit_credited": "reward",
        # Exchange types
        "BUY": "buy",
        "SELL": "sell",
    }

    def detect(self, filepath: str, first_lines: list) -> bool:
        """Return True if this looks like a Crypto.com CSV export (App or Exchange)."""
        header = " ".join(first_lines[:2]).lower() if first_lines else ""
        # App format
        if "timestamp (utc)" in header and "transaction kind" in header:
            return True
        # Exchange format
        if "trade date" in header and "pair" in header and "side" in header:
            return True
        return False

    def parse_row(self, row):
        # Detect format (App vs Exchange)
        if "Transaction Kind" in row or "Transaction Description" in row:
            return self._parse_app_row(row)
        elif "Trade Date" in row or "Pair" in row:
            return self._parse_exchange_row(row)
        else:
            return self._parse_generic_row(row)

    def _parse_app_row(self, row):
        """Parse Crypto.com App CSV."""
        timestamp = row.get("Timestamp (UTC)") or row.get("Timestamp")
        tx_kind = row.get("Transaction Kind") or ""
        description = row.get("Transaction Description") or ""
        currency = row.get("Currency") or ""
        amount = row.get("Amount") or "0"
        native_currency = row.get("Native Currency") or "CAD"
        native_amount = row.get("Native Amount") or ""

        if not timestamp:
            return None

        tx_type = self.TYPE_MAP.get(tx_kind.lower(), tx_kind.lower())

        return {
            "tx_date": self.parse_datetime(timestamp),
            "tx_type": tx_type,
            "asset": currency,
            "quantity": str(amount).replace(",", ""),
            "total_value": str(native_amount).replace(",", "") if native_amount else None,
            "currency": native_currency,
            "notes": description,
            "raw_data": dict(row),
        }

    def _parse_exchange_row(self, row):
        """Parse Crypto.com Exchange CSV."""
        timestamp = row.get("Trade Date") or row.get("Date")
        pair = row.get("Pair") or ""
        side = row.get("Side") or ""
        price = row.get("Price") or ""
        executed = row.get("Executed") or ""
        fee = row.get("Fee") or ""
        total = row.get("Total") or ""

        if not timestamp:
            return None

        # Parse pair (e.g., "BTC_USDT") — extract base asset only
        parts = pair.split("_")
        asset = parts[0] if parts else pair
        quote = parts[1] if len(parts) > 1 else "USD"

        tx_type = self.TYPE_MAP.get(side.upper(), side.lower())

        # Executed column may look like "0.1 BTC" — extract numeric part
        executed_clean = str(executed).split()[0].replace(",", "") if executed else ""

        return {
            "tx_date": self.parse_datetime(timestamp),
            "tx_type": tx_type,
            "asset": asset,
            "quantity": executed_clean,
            "price_per_unit": str(price).replace(",", "") if price else None,
            "total_value": str(total).replace(",", "") if total else None,
            "fee": str(fee).replace(",", "") if fee else None,
            "currency": quote,
            "notes": f"Pair: {pair}",
            "raw_data": dict(row),
        }

    def _parse_generic_row(self, row):
        """Try generic parsing."""
        timestamp = None
        for key in ["Timestamp", "Date", "Time", "Created"]:
            if key in row and row[key]:
                timestamp = row[key]
                break

        if not timestamp:
            return None

        quantity = None
        asset = None
        for key in ["Amount", "Quantity", "Size"]:
            if key in row and row[key]:
                quantity = row[key]
                break

        for key in ["Currency", "Asset", "Coin"]:
            if key in row and row[key]:
                asset = row[key]
                break

        if not quantity or not asset:
            return None

        return {
            "tx_date": self.parse_datetime(timestamp),
            "tx_type": "unknown",
            "asset": asset,
            "quantity": str(quantity).replace(",", ""),
            "currency": "CAD",
            "notes": str(row),
            "raw_data": dict(row),
        }
