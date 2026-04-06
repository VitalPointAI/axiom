"""Dynamic token metadata resolution via on-chain RPC calls.

Fetches ft_metadata from NEAR contracts (and EVM token info via
Etherscan/Alchemy in future) to resolve symbol + decimals.
Results are cached in the token_metadata DB table.

Usage:
    resolver = TokenMetadataResolver(db_pool)
    symbol = resolver.resolve_symbol("token.sweat", chain="near")
    # Returns "SWEAT" (fetched from chain, cached in DB)
"""

import json
import logging
from typing import Optional

import requests

from config import FASTNEAR_RPC, ALCHEMY_API_KEY

logger = logging.getLogger(__name__)

# In-memory cache to avoid DB lookups within the same sync run
_mem_cache: dict[str, dict] = {}

# Hardcoded fallbacks for tokens where RPC is unreliable or contract
# doesn't implement ft_metadata (e.g. system accounts, bridges)
_FALLBACK_SYMBOLS: dict[str, str] = {
    "near": "NEAR",
    "wrap.near": "NEAR",
}


class TokenMetadataResolver:
    """Resolve token contract IDs to symbols using on-chain metadata.

    Checks (in order):
    1. In-memory cache (per-process, survives across sync calls)
    2. DB token_metadata table
    3. On-chain RPC ft_metadata call (result cached to DB)
    4. Hardcoded fallback map (for system tokens)
    5. Returns contract_id uppercased as last resort
    """

    def __init__(self, db_pool):
        self.pool = db_pool

    def resolve_symbol(self, contract_id: str, chain: str = "near") -> str:
        """Resolve a token contract to its symbol.

        Args:
            contract_id: The token contract address/account.
            chain: Chain name (currently only 'near' does RPC lookup).

        Returns:
            Canonical uppercase symbol string.
        """
        if not contract_id:
            if chain == "near":
                return "NEAR"
            return "UNKNOWN"

        key = f"{chain}:{contract_id.lower()}"

        # 1. In-memory cache
        if key in _mem_cache:
            cached = _mem_cache[key]
            if cached.get("symbol"):
                return cached["symbol"]

        # 2. DB cache
        db_meta = self._db_lookup(contract_id, chain)
        if db_meta and db_meta.get("symbol"):
            _mem_cache[key] = db_meta
            return db_meta["symbol"]

        # 3. Hardcoded fallback (system tokens)
        lower = contract_id.lower()
        if lower in _FALLBACK_SYMBOLS:
            symbol = _FALLBACK_SYMBOLS[lower]
            self._db_upsert(contract_id, chain, symbol=symbol, decimals=24, name=contract_id)
            _mem_cache[key] = {"symbol": symbol, "decimals": 24}
            return symbol

        # 4. On-chain RPC
        if chain == "near":
            meta = self._fetch_near_ft_metadata(contract_id)
        elif contract_id.startswith("0x") or contract_id.startswith("0X"):
            meta = self._fetch_evm_token_metadata(contract_id, chain)
        else:
            meta = None

        if meta and meta.get("symbol"):
            symbol = meta["symbol"].upper()
            self._db_upsert(
                contract_id, chain,
                symbol=symbol,
                decimals=meta.get("decimals"),
                name=meta.get("name"),
                icon_url=meta.get("icon") or meta.get("logo"),
            )
            _mem_cache[key] = {"symbol": symbol, "decimals": meta.get("decimals")}
            return symbol
        else:
            self._db_mark_failed(contract_id, chain)

        # 5. Last resort — use contract ID
        fallback = contract_id.split(".")[0].upper() if "." in contract_id else contract_id.upper()
        _mem_cache[key] = {"symbol": fallback}
        return fallback

    def resolve_decimals(self, contract_id: str, chain: str = "near") -> int:
        """Get token decimals for proper amount conversion.

        Returns 24 for NEAR native, 18 for EVM native, or the on-chain value.
        """
        if not contract_id:
            return 24 if chain == "near" else 18

        key = f"{chain}:{contract_id.lower()}"
        if key in _mem_cache and "decimals" in _mem_cache[key]:
            return _mem_cache[key]["decimals"]

        # Trigger full resolution which populates decimals
        self.resolve_symbol(contract_id, chain)

        if key in _mem_cache and _mem_cache[key].get("decimals") is not None:
            return _mem_cache[key]["decimals"]

        return 24 if chain == "near" else 18

    # ------------------------------------------------------------------
    # NEAR RPC
    # ------------------------------------------------------------------

    def _fetch_near_ft_metadata(self, contract_id: str) -> Optional[dict]:
        """Call ft_metadata on a NEAR contract via RPC.

        Returns dict with keys: spec, name, symbol, icon, decimals
        or None on failure.
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": "ft-meta",
                "method": "query",
                "params": {
                    "request_type": "call_function",
                    "account_id": contract_id,
                    "method_name": "ft_metadata",
                    "args_base64": "",
                    "finality": "final",
                },
            }
            resp = requests.post(FASTNEAR_RPC, json=payload, timeout=5)
            data = resp.json()

            result_bytes = data.get("result", {}).get("result")
            if not result_bytes:
                return None

            result_str = bytes(result_bytes).decode("utf-8")
            return json.loads(result_str)
        except Exception as e:
            logger.debug("ft_metadata failed for %s: %s", contract_id, e)
            return None

    # ------------------------------------------------------------------
    # EVM — Alchemy getTokenMetadata
    # ------------------------------------------------------------------

    # Map chain names to Alchemy network prefixes
    _ALCHEMY_NETWORKS = {
        "ethereum": "eth-mainnet",
        "polygon": "polygon-mainnet",
        "optimism": "opt-mainnet",
        "arbitrum": "arb-mainnet",
    }

    def _fetch_evm_token_metadata(self, contract_address: str, chain: str = "ethereum") -> Optional[dict]:
        """Fetch ERC-20 token metadata via Alchemy getTokenMetadata.

        Returns dict with keys: symbol, name, decimals, logo
        or None on failure.
        """
        if not ALCHEMY_API_KEY:
            logger.debug("ALCHEMY_API_KEY not set, cannot resolve EVM token %s", contract_address)
            return None

        network = self._ALCHEMY_NETWORKS.get(chain, "eth-mainnet")
        url = f"https://{network}.g.alchemy.com/v2/{ALCHEMY_API_KEY}"

        try:
            resp = requests.post(
                url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "alchemy_getTokenMetadata",
                    "params": [contract_address],
                },
                timeout=10,
            )
            data = resp.json()
            result = data.get("result")
            if not result:
                return None

            symbol = result.get("symbol")
            if not symbol:
                return None

            return {
                "symbol": symbol,
                "name": result.get("name", ""),
                "decimals": result.get("decimals"),
                "logo": result.get("logo", ""),
            }
        except Exception as e:
            logger.debug("Alchemy getTokenMetadata failed for %s on %s: %s",
                         contract_address, chain, e)
            return None

    def resolve_all_unresolved(self, chain: str = "ethereum"):
        """Bulk resolve all unresolved EVM tokens in the transactions table.

        Queries distinct token_ids that start with 0x and don't have
        entries in token_metadata, then resolves each via Alchemy.
        """
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT LOWER(t.token_id)
                FROM transactions t
                WHERE t.token_id LIKE '0x%%' OR t.token_id LIKE '0X%%'
                  AND LOWER(t.token_id) NOT IN (
                      SELECT contract_id FROM token_metadata WHERE fetch_failed = FALSE
                  )
                """,
            )
            unresolved = [row[0] for row in cur.fetchall()]
            cur.close()
        finally:
            self.pool.putconn(conn)

        resolved = 0
        for contract_id in unresolved:
            # Check if already in DB
            existing = self._db_lookup(contract_id, chain)
            if existing and existing.get("symbol"):
                continue

            symbol = self.resolve_symbol(contract_id, chain)
            if symbol and not symbol.startswith("0X"):
                resolved += 1
                logger.info("Resolved EVM token %s → %s", contract_id[:10], symbol)

        logger.info("Resolved %d/%d EVM tokens", resolved, len(unresolved))
        return resolved

    # ------------------------------------------------------------------
    # DB operations
    # ------------------------------------------------------------------

    def _db_lookup(self, contract_id: str, chain: str) -> Optional[dict]:
        """Look up cached metadata from DB."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT symbol, decimals, name, icon_url, fetch_failed
                   FROM token_metadata
                   WHERE contract_id = %s AND chain = %s""",
                (contract_id.lower(), chain),
            )
            row = cur.fetchone()
            cur.close()
            if row:
                symbol, decimals, name, icon_url, fetch_failed = row
                if fetch_failed:
                    return {"symbol": None, "fetch_failed": True}
                return {
                    "symbol": symbol,
                    "decimals": decimals,
                    "name": name,
                    "icon_url": icon_url,
                }
            return None
        finally:
            self.pool.putconn(conn)

    def _db_upsert(self, contract_id, chain, symbol=None, decimals=None, name=None, icon_url=None):
        """Insert or update token metadata in DB."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO token_metadata (contract_id, chain, symbol, decimals, name, icon_url, fetch_failed)
                   VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                   ON CONFLICT (contract_id) DO UPDATE SET
                       symbol = EXCLUDED.symbol,
                       decimals = EXCLUDED.decimals,
                       name = EXCLUDED.name,
                       icon_url = EXCLUDED.icon_url,
                       fetch_failed = FALSE,
                       fetched_at = NOW()""",
                (contract_id.lower(), chain, symbol, decimals, name, icon_url),
            )
            conn.commit()
            cur.close()
        finally:
            self.pool.putconn(conn)

    def _db_mark_failed(self, contract_id, chain):
        """Mark a contract as failed so we don't retry on every sync."""
        conn = self.pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO token_metadata (contract_id, chain, fetch_failed)
                   VALUES (%s, %s, TRUE)
                   ON CONFLICT (contract_id) DO UPDATE SET
                       fetch_failed = TRUE,
                       fetched_at = NOW()""",
                (contract_id.lower(), chain),
            )
            conn.commit()
            cur.close()
        finally:
            self.pool.putconn(conn)
