"""Chain fetcher plugin interface for Axiom multi-chain indexer.

Architecture overview
---------------------
Every chain integration is implemented as a concrete subclass of ChainFetcher.
The IndexerService registers all fetchers in its ``handlers`` dict, keyed by
job_type (e.g. ``'evm_full_sync'``, ``'near_full_sync'``).  When a job is
claimed from ``indexing_jobs`` the service dispatches to the appropriate handler
via ``sync_wallet()``.

Supported chain models
----------------------
- Account-based:  ETH/EVM, NEAR, Cosmos SDK (Akash), XRP, Sweat
- UTXO-based:     BTC (future)
- Unique:         Solana (future)

Job dict contract
-----------------
The ``job`` dict passed to ``sync_wallet()`` is produced by the indexer
service's ``_claim_next_job()`` which JOINs ``indexing_jobs`` with ``wallets``.
Required keys::

    id            int   — job row PK (for status updates)
    user_id       int
    wallet_id     int
    chain         str   — e.g. 'ethereum', 'near', 'akash'
    cursor        str   — resume point (block height, page token, etc.)
    job_type      str   — e.g. 'evm_full_sync', 'evm_incremental'
    attempts      int   — retry counter
    account_id    str   — wallet address / account identifier (from wallets JOIN)
"""

from abc import ABC, abstractmethod

from psycopg2.pool import SimpleConnectionPool

__all__ = ["ChainFetcher"]


class ChainFetcher(ABC):
    """Abstract base class for all chain fetcher plugins.

    Every chain fetcher is registered in service.py handlers dict
    and dispatched by job_type. The job dict comes from _claim_next_job()
    which JOINs indexing_jobs with wallets.

    Chain models supported:
    - Account-based: ETH, NEAR, Cosmos SDK (Akash), XRP, Sweat
    - UTXO-based: BTC (future)
    - Unique: Solana (future)
    """

    chain_name: str = ""            # e.g. 'ethereum', 'near', 'akash'
    supported_job_types: list = []  # e.g. ['evm_full_sync', 'evm_incremental']

    def __init__(self, pool: SimpleConnectionPool):
        self.pool = pool

    @abstractmethod
    def sync_wallet(self, job: dict) -> None:
        """Process a full_sync or incremental_sync job.

        Args:
            job: dict with keys: id, user_id, wallet_id, chain, cursor,
                 job_type, attempts, account_id (from wallets JOIN)

        Must:
        - Fetch transactions from external API
        - Upsert into transactions table (ON CONFLICT DO NOTHING)
        - Update job cursor to resume point
        - Update job progress_fetched
        """
        pass

    @abstractmethod
    def get_balance(self, address: str) -> dict:
        """Get current on-chain balance for reconciliation.

        Args:
            address: wallet address / account identifier

        Returns:
            dict with keys:
                native_balance (str): native token balance as a string
                tokens (list[dict]): list of token balances, each with
                    at minimum ``token_id`` and ``balance`` keys
        """
        pass
