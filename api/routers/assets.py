"""Assets API — per-token holdings with wallet breakdown and filtering.

Endpoints:
  GET  /api/assets         — token holdings aggregated from ACB snapshots
  POST /api/assets/spam    — mark a token as spam
  DELETE /api/assets/spam  — unmark a token as spam

Data source: acb_snapshots (latest per user+token) joined with wallets
for per-wallet breakdown via raw transaction replay.
"""

import logging
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

from api.dependencies import get_effective_user, get_pool_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assets", tags=["assets"])

# Chain display names
CHAIN_NAMES = {
    "near": "NEAR",
    "ethereum": "Ethereum",
    "polygon": "Polygon",
    "optimism": "Optimism",
    "cronos": "Cronos",
    "exchange": "Exchange",
}


@router.get("")
async def get_assets(
    chain: Optional[str] = Query(default=None),
    asset: Optional[str] = Query(default=None),
    wallet: Optional[str] = Query(default=None),
    date: Optional[str] = Query(default=None),
    hideSmall: bool = Query(default=True),
    includeSpam: bool = Query(default=False),
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Return token holdings with wallet breakdown and filters.

    Aggregates from acb_snapshots (latest per token) for balances,
    and price_cache for current prices. Wallet-level breakdown uses
    raw transaction replay per wallet.
    """
    user_id = user["user_id"]

    def _query(conn):
        cur = conn.cursor()
        try:
            # Latest ACB snapshot per token
            cur.execute(
                """
                SELECT token_symbol, units_after, acb_per_unit_cad, total_cost_cad
                FROM (
                    SELECT token_symbol, units_after, acb_per_unit_cad, total_cost_cad,
                           ROW_NUMBER() OVER (
                               PARTITION BY token_symbol
                               ORDER BY block_timestamp DESC
                           ) AS rn
                    FROM acb_snapshots
                    WHERE user_id = %s
                ) ranked
                WHERE rn = 1 AND units_after > 0
                ORDER BY token_symbol
                """,
                (user_id,),
            )
            acb_rows = cur.fetchall()

            # Get latest USD prices from price_cache
            cur.execute(
                """
                SELECT DISTINCT ON (coin_id)
                    coin_id, price, date
                FROM price_cache
                WHERE currency = 'usd'
                ORDER BY coin_id, date DESC
                """,
            )
            price_rows = cur.fetchall()
            prices = {}
            for coin_id, price, _ in price_rows:
                prices[coin_id] = float(price) if price else 0.0

            # Get wallets for this user
            cur.execute(
                "SELECT id, account_id, chain, label FROM wallets WHERE user_id = %s",
                (user_id,),
            )
            wallet_rows = cur.fetchall()
            wallets_by_id = {}
            for wid, account_id, w_chain, label in wallet_rows:
                wallets_by_id[wid] = {
                    "id": wid,
                    "address": account_id,
                    "chain": (w_chain or "").lower(),
                    "label": label or "",
                }

            # Per-wallet balance breakdown via transaction replay
            # Uses token_metadata table for dynamic symbol resolution
            # if available; falls back to UPPER(token_id) for unmapped tokens.
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'token_metadata')"
            )
            has_token_metadata = cur.fetchone()[0]

            if has_token_metadata:
                cur.execute(
                    """
                    SELECT t.wallet_id,
                           CASE
                               WHEN t.token_id IS NOT NULL THEN
                                   COALESCE(tm.symbol, UPPER(t.token_id))
                               WHEN LOWER(t.chain) = 'near' THEN 'NEAR'
                               WHEN LOWER(t.chain) IN ('ethereum','polygon','optimism','cronos') THEN 'ETH'
                               ELSE 'UNKNOWN'
                           END AS token,
                           LOWER(t.chain) AS chain,
                           SUM(CASE WHEN t.direction = 'in' THEN t.amount ELSE 0 END) AS total_in,
                           SUM(CASE WHEN t.direction = 'out' THEN t.amount ELSE 0 END) AS total_out,
                           SUM(CASE WHEN t.direction = 'out' THEN COALESCE(t.fee, 0) ELSE 0 END) AS total_fees
                    FROM transactions t
                    LEFT JOIN token_metadata tm ON LOWER(t.token_id) = tm.contract_id
                    WHERE t.user_id = %s
                    GROUP BY t.wallet_id, token, LOWER(t.chain)
                    """,
                    (user_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT t.wallet_id,
                           CASE
                               WHEN t.token_id IS NOT NULL THEN UPPER(t.token_id)
                               WHEN LOWER(t.chain) = 'near' THEN 'NEAR'
                               WHEN LOWER(t.chain) IN ('ethereum','polygon','optimism','cronos') THEN 'ETH'
                               ELSE 'UNKNOWN'
                           END AS token,
                           LOWER(t.chain) AS chain,
                           SUM(CASE WHEN t.direction = 'in' THEN t.amount ELSE 0 END) AS total_in,
                           SUM(CASE WHEN t.direction = 'out' THEN t.amount ELSE 0 END) AS total_out,
                           SUM(CASE WHEN t.direction = 'out' THEN COALESCE(t.fee, 0) ELSE 0 END) AS total_fees
                    FROM transactions t
                    WHERE t.user_id = %s
                    GROUP BY t.wallet_id, token, LOWER(t.chain)
                    """,
                    (user_id,),
                )
            wallet_balance_rows = cur.fetchall()

            # Available snapshot dates
            cur.execute(
                """
                SELECT DISTINCT DATE(TO_TIMESTAMP(block_timestamp / 1e9))
                FROM acb_snapshots
                WHERE user_id = %s AND block_timestamp > 1e18
                UNION
                SELECT DISTINCT DATE(TO_TIMESTAMP(block_timestamp))
                FROM acb_snapshots
                WHERE user_id = %s AND block_timestamp <= 1e18 AND block_timestamp > 0
                ORDER BY 1 DESC
                LIMIT 30
                """,
                (user_id, user_id),
            )
            snapshot_dates = [str(r[0]) for r in cur.fetchall() if r[0]]

            # Spam tokens (rule_type='token_symbol', value=symbol)
            cur.execute(
                """SELECT DISTINCT value FROM spam_rules
                   WHERE user_id = %s AND rule_type = 'token_symbol' AND is_active = TRUE""",
                (user_id,),
            )
            spam_tokens = {r[0] for r in cur.fetchall()}

            return acb_rows, prices, wallets_by_id, wallet_balance_rows, snapshot_dates, spam_tokens
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        (acb_rows, prices, wallets_by_id, wallet_balance_rows,
         snapshot_dates, spam_tokens) = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    # Symbol -> CoinGecko ID mapping for price lookups
    symbol_to_coin = {
        "NEAR": "near", "ETH": "ethereum", "MATIC": "matic-network",
        "CRO": "crypto-com-chain", "USDC": "usd-coin", "USDT": "tether",
        "DAI": "dai", "WETH": "ethereum", "WNEAR": "near",
        "SOL": "solana", "ALGO": "algorand", "GRT": "the-graph",
        "UNI": "uniswap", "MANA": "decentraland", "GTC": "gitcoin",
        "AKT": "akash-network", "SKL": "skale",
    }

    # Chain divisors for raw -> human units
    chain_divisors = {
        "near": Decimal("1" + "0" * 24),
        "ethereum": Decimal("1" + "0" * 18),
        "polygon": Decimal("1" + "0" * 18),
        "optimism": Decimal("1" + "0" * 18),
        "cronos": Decimal("1" + "0" * 18),
    }

    # Build per-wallet token balances
    wallet_token_balances: dict[str, dict[int, float]] = {}  # token -> {wallet_id: balance}
    for wid, token, w_chain, total_in, total_out, total_fees in wallet_balance_rows:
        divisor = chain_divisors.get(w_chain, Decimal("1" + "0" * 24))
        bal_in = Decimal(str(total_in or 0)) / divisor
        bal_out = Decimal(str(total_out or 0)) / divisor
        bal_fees = Decimal(str(total_fees or 0)) / divisor
        balance = float(bal_in - bal_out - bal_fees)
        if balance > 0.000001:
            wallet_token_balances.setdefault(token, {})[wid] = balance

    # Build asset list from ACB snapshots + wallet balances.
    # ACB snapshots are authoritative when available; for tokens only in
    # wallet_token_balances (ACB hasn't run yet), use transaction-derived balances.
    assets = []
    all_chains = set()
    all_asset_names = set()
    acb_symbols = set()

    for token_symbol, units_after, acb_per_unit, total_cost in acb_rows:
        acb_symbols.add(token_symbol)
        balance = float(units_after)
        if balance <= 0:
            continue

        is_spam = token_symbol in spam_tokens
        if is_spam and not includeSpam:
            continue

        # Get price
        coin_id = symbol_to_coin.get(token_symbol, token_symbol.lower())
        price_usd = prices.get(coin_id, 0.0)
        value_usd = balance * price_usd

        if hideSmall and value_usd < 1.0 and price_usd > 0:
            continue

        # Determine chain from wallet balances or default
        token_chain = "near"  # default
        wallet_balances = wallet_token_balances.get(token_symbol, {})
        for wid in wallet_balances:
            w = wallets_by_id.get(wid)
            if w:
                token_chain = w["chain"]
                break

        # Apply filters
        if chain and token_chain != chain.lower():
            continue
        if asset and token_symbol != asset.upper():
            continue

        # Build wallet list
        wallet_list = []
        for wid, w_balance in wallet_balances.items():
            w = wallets_by_id.get(wid)
            if not w:
                continue
            if wallet and wallet.lower() not in w["address"].lower():
                continue
            wallet_list.append({
                "address": w["address"],
                "label": w["label"],
                "balance": w_balance,
                "value_usd": w_balance * price_usd,
            })

        if wallet and not wallet_list:
            continue

        # If no wallet breakdown available, create a single entry
        if not wallet_list:
            wallet_list = [{
                "address": "aggregated",
                "label": "All wallets",
                "balance": balance,
                "value_usd": value_usd,
            }]

        all_chains.add(token_chain)
        all_asset_names.add(token_symbol)

        assets.append({
            "asset": token_symbol,
            "chain": token_chain,
            "chain_name": CHAIN_NAMES.get(token_chain, token_chain.upper()),
            "balance": balance,
            "price_usd": price_usd,
            "value_usd": value_usd,
            "is_spam": is_spam,
            "wallets": sorted(wallet_list, key=lambda w: -w["balance"]),
        })

    # Add tokens from wallet balances that don't have ACB snapshots yet
    for token_symbol, wallet_bals in wallet_token_balances.items():
        if token_symbol in acb_symbols:
            continue  # Already handled above

        total_balance = sum(wallet_bals.values())
        if total_balance <= 0.000001:
            continue

        is_spam = token_symbol in spam_tokens
        if is_spam and not includeSpam:
            continue

        coin_id = symbol_to_coin.get(token_symbol, token_symbol.lower())
        price_usd = prices.get(coin_id, 0.0)
        value_usd = total_balance * price_usd

        if hideSmall and value_usd < 1.0 and price_usd > 0:
            continue

        token_chain = "near"
        for wid in wallet_bals:
            w = wallets_by_id.get(wid)
            if w:
                token_chain = w["chain"]
                break

        if chain and token_chain != chain.lower():
            continue
        if asset and token_symbol != asset.upper():
            continue

        wallet_list = []
        for wid, w_balance in wallet_bals.items():
            w = wallets_by_id.get(wid)
            if not w:
                continue
            if wallet and wallet.lower() not in w["address"].lower():
                continue
            wallet_list.append({
                "address": w["address"],
                "label": w["label"],
                "balance": w_balance,
                "value_usd": w_balance * price_usd,
            })

        if wallet and not wallet_list:
            continue

        if not wallet_list:
            wallet_list = [{
                "address": "aggregated",
                "label": "All wallets",
                "balance": total_balance,
                "value_usd": value_usd,
            }]

        all_chains.add(token_chain)
        all_asset_names.add(token_symbol)

        assets.append({
            "asset": token_symbol,
            "chain": token_chain,
            "chain_name": CHAIN_NAMES.get(token_chain, token_chain.upper()),
            "balance": total_balance,
            "price_usd": price_usd,
            "value_usd": value_usd,
            "is_spam": is_spam,
            "wallets": sorted(wallet_list, key=lambda w: -w["balance"]),
        })

    # Sort by value descending
    assets.sort(key=lambda a: -a["value_usd"])
    total_value = sum(a["value_usd"] for a in assets)

    return {
        "assets": assets,
        "totalValueUsd": total_value,
        "filters": {
            "chains": [{"value": c, "label": CHAIN_NAMES.get(c, c.upper())} for c in sorted(all_chains)],
            "assets": sorted(all_asset_names),
            "wallets": [],
        },
        "snapshotDates": snapshot_dates[:20],
        "isHistorical": bool(date),
    }


@router.post("/spam")
async def mark_as_spam(
    body: dict,
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Mark a token as spam for this user."""
    user_id = user["user_id"]
    token_symbol = body.get("token_symbol", "")
    reason = body.get("reason", "User marked")

    def _insert(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """INSERT INTO spam_rules (user_id, rule_type, value, created_by, is_active, created_at)
                   VALUES (%s, 'token_symbol', %s, %s, TRUE, NOW())
                   ON CONFLICT DO NOTHING""",
                (user_id, token_symbol, reason),
            )
            conn.commit()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        await run_in_threadpool(_insert, conn)
    finally:
        pool.putconn(conn)

    return {"ok": True}


@router.delete("/spam")
async def unmark_spam(
    token_symbol: str = Query(...),
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    """Remove spam flag for a token."""
    user_id = user["user_id"]

    def _delete(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """UPDATE spam_rules SET is_active = FALSE
                   WHERE user_id = %s AND rule_type = 'token_symbol' AND value = %s""",
                (user_id, token_symbol),
            )
            conn.commit()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        await run_in_threadpool(_delete, conn)
    finally:
        pool.putconn(conn)

    return {"ok": True}
