"""Base class for exchange CSV parsers."""

import csv
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from indexers.exchange_plugin import ExchangeParser

logger = logging.getLogger(__name__)


class BaseExchangeParser(ExchangeParser):
    """Base class for exchange CSV parsers.

    Implements the ExchangeParser ABC using PostgreSQL via indexers.db.
    Subclasses must implement parse_row() and detect().
    """

    exchange_name: str = "unknown"
    supported_formats: list = ["csv"]

    def __init__(self):
        self.transactions: List[dict] = []
        self.errors: List[str] = []

    def detect(self, filepath: str, first_lines: list) -> bool:
        """Default detect — always returns False. Subclasses override."""
        return False

    def parse_row(self, row: dict) -> Optional[dict]:
        """Parse a single CSV row into standardized format.

        Should return dict with:
        - tx_id: exchange's internal ID (optional, generates hash if absent)
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
        - raw_data: dict of original row data (for JSONB)
        """
        raise NotImplementedError("Subclasses must implement parse_row()")

    def validate_parsed_row(self, parsed: dict, raw_row: dict) -> dict:
        """Post-parse invariant validation. Flag + continue pattern.

        Checks amount is non-zero, date is parseable, asset is non-empty.
        Sets needs_review=True on violations, never returns None.
        """
        violations = []

        amount = parsed.get("quantity") or parsed.get("amount")
        if amount is None or amount == 0 or amount == Decimal("0") or amount == "0":
            violations.append("zero_or_missing_amount")

        if parsed.get("tx_date") is None:
            violations.append("missing_date")

        if not parsed.get("asset"):
            violations.append("missing_asset")

        if violations:
            logger.warning(
                "Exchange parser invariant violation in %s row: %s",
                self.exchange_name, violations,
            )
            parsed["needs_review"] = True
            parsed["_invariant_violations"] = violations

        return parsed

    def parse_file(self, filepath: str) -> List[dict]:
        """Parse a CSV file and return list of standardized transaction dicts."""
        self.transactions = []
        self.errors = []

        with open(filepath, "r", encoding="utf-8-sig") as f:
            # Try to detect delimiter
            sample = f.read(4096)
            f.seek(0)

            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel

            reader = csv.DictReader(f, dialect=dialect)

            for i, row in enumerate(reader, 1):
                try:
                    tx = self.parse_row(row)
                    if tx:
                        tx = self.validate_parsed_row(tx, row)
                        tx["_row"] = i
                        # Ensure raw_data is a dict (JSONB-compatible)
                        if "raw_data" not in tx:
                            tx["raw_data"] = dict(row)
                        elif not isinstance(tx["raw_data"], dict):
                            tx["raw_data"] = dict(row)
                        self.transactions.append(tx)
                except Exception as e:
                    self.errors.append(f"Row {i}: {e}")

        return self.transactions

    def import_to_db(
        self,
        filepath: str,
        user_id: int,
        pool,
        batch_id: Optional[str] = None,
    ) -> dict:
        """Parse file and import transactions into exchange_transactions (PostgreSQL).

        Uses %s placeholders (psycopg2), user_id parameter, and
        ON CONFLICT (user_id, exchange, tx_id) DO NOTHING for deduplication.

        Args:
            filepath: path to the CSV file
            user_id: owner of the imported records
            pool: psycopg2 SimpleConnectionPool from indexers/db.py
            batch_id: optional import batch identifier

        Returns:
            dict with keys: imported, skipped, errors, batch_id
        """
        batch_id = batch_id or datetime.now().strftime("%Y%m%d_%H%M%S")

        transactions = self.parse_file(filepath)

        imported = 0
        skipped = 0
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            for tx in transactions:
                try:
                    # Generate a tx_id if not provided
                    tx_id = tx.get("tx_id")
                    if not tx_id:
                        # Build a deterministic ID from key fields
                        tx_id = "_".join([
                            str(tx.get("tx_date", "")),
                            str(tx.get("asset", "")),
                            str(tx.get("quantity", "")),
                            str(tx.get("tx_type", "")),
                        ])

                    # raw_data must be a dict; serialize to JSON string for psycopg2
                    raw_data = tx.get("raw_data", {})
                    if not isinstance(raw_data, dict):
                        raw_data = {}
                    raw_data_json = json.dumps(raw_data)

                    cur.execute(
                        """
                        INSERT INTO exchange_transactions
                            (user_id, exchange, tx_id, tx_date, tx_type, asset,
                             quantity, price_per_unit, total_value, fee, fee_asset,
                             currency, notes, raw_data, import_batch, source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'csv')
                        ON CONFLICT (user_id, exchange, tx_id) DO NOTHING
                        """,
                        (
                            user_id,
                            self.exchange_name,
                            tx_id,
                            tx.get("tx_date"),
                            tx.get("tx_type"),
                            tx.get("asset"),
                            tx.get("quantity"),
                            tx.get("price_per_unit"),
                            tx.get("total_value"),
                            tx.get("fee"),
                            tx.get("fee_asset"),
                            tx.get("currency", "CAD"),
                            tx.get("notes"),
                            raw_data_json,
                            batch_id,
                        ),
                    )
                    # rowcount 1 = inserted; 0 = skipped (ON CONFLICT)
                    if cur.rowcount == 1:
                        imported += 1
                    else:
                        skipped += 1
                except Exception as e:
                    self.errors.append(f"DB insert: {e}")

            conn.commit()
        finally:
            pool.putconn(conn)

        return {
            "imported": imported,
            "skipped": skipped,
            "errors": len(self.errors),
            "batch_id": batch_id,
        }

    @staticmethod
    def parse_datetime(date_str: str, formats=None) -> datetime:
        """Try parsing datetime with multiple formats."""
        formats = formats or [
            "%Y-%m-%d %H:%M:%S UTC",
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
