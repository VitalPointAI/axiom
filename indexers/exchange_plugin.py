"""Exchange plugin interfaces for Axiom multi-exchange integration.

Architecture overview
---------------------
Exchange integrations are implemented via two separate ABCs:

ExchangeParser
    Used by the ``file_import`` job handler.  Each parser knows how to read a
    specific exchange's CSV/XLSX/PDF export format and produce standardized
    transaction records for insertion into ``exchange_transactions``.

ExchangeConnector
    Used by ``exchange_sync`` jobs.  Connectors authenticate against an
    exchange's REST API using credentials stored in ``exchange_connections``
    and fetch transaction history directly.

Standardized transaction dict
------------------------------
Both ``ExchangeParser.parse_file()`` and ``ExchangeConnector.fetch_transactions()``
return lists of dicts with these keys::

    tx_id           str            — exchange's internal ID (dedup key)
    tx_date         datetime       — timezone-aware preferred
    tx_type         str            — 'buy', 'sell', 'send', 'receive',
                                     'staking_reward', 'interest', etc.
    asset           str            — 'BTC', 'ETH', 'NEAR', etc.
    quantity        str            — preserve decimal precision
    price_per_unit  str | None
    total_value     str | None
    fee             str | None
    fee_asset       str | None
    currency        str            — 'CAD', 'USD', etc.
    notes           str | None
    raw_data        dict           — original row / API response data

Database insertion uses ``%s`` placeholders (psycopg2) and
``ON CONFLICT DO NOTHING`` for idempotent re-import.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from psycopg2.pool import SimpleConnectionPool

__all__ = ["ExchangeParser", "ExchangeConnector"]


class ExchangeParser(ABC):
    """Abstract base class for exchange file parsers (CSV, XLSX, PDF).

    Parsers are used by the file_import job handler to process uploaded
    exchange export files. Each parser knows how to read a specific
    exchange's export format and extract standardized transaction records.
    """

    exchange_name: str = ""
    supported_formats: list = ["csv"]  # 'csv', 'xlsx', 'pdf'

    @abstractmethod
    def detect(self, filepath: str, first_lines: list) -> bool:
        """Return True if this parser can handle the given file.

        Args:
            filepath: path to the file
            first_lines: first 5 lines of the file (for header detection)

        Returns:
            True if the parser recognises the file format, False otherwise.
        """
        pass

    @abstractmethod
    def parse_file(self, filepath: str) -> List[dict]:
        """Parse file and return list of standardized transaction dicts.

        Each dict must have keys:
        - tx_id: str (exchange's internal ID, for dedup)
        - tx_date: datetime
        - tx_type: str ('buy', 'sell', 'send', 'receive', etc.)
        - asset: str ('BTC', 'ETH', 'NEAR', etc.)
        - quantity: str (preserve precision)
        - price_per_unit: str or None
        - total_value: str or None
        - fee: str or None
        - fee_asset: str or None
        - currency: str ('CAD', 'USD')
        - notes: str or None
        - raw_data: dict (original row data)
        """
        pass

    @abstractmethod
    def import_to_db(
        self,
        filepath: str,
        user_id: int,
        pool: SimpleConnectionPool,
        batch_id: Optional[str] = None,
    ) -> dict:
        """Parse file and insert into exchange_transactions table.

        Uses %s placeholders (psycopg2), ON CONFLICT DO NOTHING for dedup.

        Args:
            filepath: path to the file to import
            user_id: owner of the imported records
            pool: psycopg2 connection pool from indexers/db.py
            batch_id: optional import batch identifier for grouping records

        Returns:
            dict with keys:
                imported (int): rows successfully inserted
                skipped (int): rows skipped due to ON CONFLICT
                errors (int): rows that raised exceptions
                batch_id (str): the batch identifier used
        """
        pass


class ExchangeConnector(ABC):
    """Abstract base class for exchange API connectors.

    Connectors use exchange API keys to fetch transaction history
    directly. They are triggered by exchange_sync jobs in the queue.
    """

    exchange_name: str = ""

    def __init__(self, pool: SimpleConnectionPool):
        self.pool = pool

    @abstractmethod
    def connect(self, api_key: str, api_secret: str = None, **kwargs) -> bool:
        """Validate API credentials. Return True if connection successful.

        Args:
            api_key: primary API key
            api_secret: API secret (optional, depends on exchange)
            **kwargs: additional auth parameters (e.g. passphrase, sub-account)

        Returns:
            True if credentials are valid and the connection succeeded.
        """
        pass

    @abstractmethod
    def fetch_transactions(
        self, user_id: int, since: Optional[str] = None
    ) -> List[dict]:
        """Fetch transactions from exchange API.

        Args:
            user_id: for tagging imported records
            since: cursor/timestamp for incremental sync (ISO-8601 or exchange
                   specific pagination token); None means full history fetch

        Returns:
            List of standardized transaction dicts — same format as
            ExchangeParser.parse_file() return value.
        """
        pass

    @abstractmethod
    def get_balances(self) -> dict:
        """Get current exchange account balances for reconciliation.

        Returns:
            dict mapping asset symbol to balance string, e.g.
            ``{'BTC': '0.12345678', 'ETH': '1.5', 'CAD': '250.00'}``
        """
        pass
