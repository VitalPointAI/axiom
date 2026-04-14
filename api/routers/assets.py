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

import db.crypto as _crypto
from api.dependencies import get_effective_user_with_dek, get_pool_dep

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


def _dec_str(raw) -> Optional[str]:
    """Decrypt raw BYTEA from psycopg2 using the current context DEK.

    If raw is already a str (e.g. in tests where mocks return plaintext),
    return it unchanged — EncryptedBytes.process_result_value() operates on bytes only.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    v = _crypto.EncryptedBytes().process_result_value(bytes(raw), None)
    return str(v) if v is not None else None


@router.get("")
async def get_assets(
    chain: Optional[str] = Query(default=None),
    asset: Optional[str] = Query(default=None),
    wallet: Optional[str] = Query(default=None),
    date: Optional[str] = Query(default=None),
    hideSmall: bool = Query(default=True),
    includeSpam: bool = Query(default=False),
    user: dict = Depends(get_effective_user_with_dek),
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
            # D-07: acb_snapshots.token_symbol and units_after are encrypted.
            # Fetch all rows for user, decrypt in Python, then find latest per token.
            cur.execute(
                """
                SELECT token_symbol, units_after, acb_per_unit_cad, total_cost_cad, block_timestamp
                FROM acb_snapshots
                WHERE user_id = %s
                ORDER BY block_timestamp DESC
                """,
                (user_id,),
            )
            acb_rows_raw = cur.fetchall()

            # Get latest USD prices from price_cache (public data — cleartext)
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

            # Get wallets for this user — account_id is encrypted
            cur.execute(
                "SELECT id, account_id, chain, label FROM wallets WHERE user_id = %s",
                (user_id,),
            )
            wallet_rows = cur.fetchall()

            # D-07: Per-wallet native balance from transaction replay (NEAR/ETH).
            # direction and amount are encrypted — fetch raw rows, aggregate in Python.
            cur.execute(
                """
                SELECT t.wallet_id, LOWER(t.chain) AS chain, t.direction, t.amount, t.fee, t.token_id
                FROM transactions t
                WHERE t.user_id = %s
                """,
                (user_id,),
            )
            tx_raw_rows = cur.fetchall()

            # Available snapshot dates (block_timestamp is cleartext)
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

            # D-07: Spam rules. User-scoped rules use rule_type_enc and value_enc (encrypted).
            # Fetch all active user spam rules, decrypt in Python.
            cur.execute(
                """SELECT rule_type_enc, value_enc FROM spam_rules
                   WHERE user_id = %s AND is_active = TRUE""",
                (user_id,),
            )
            spam_rows = cur.fetchall()

            return acb_rows_raw, prices, wallet_rows, tx_raw_rows, snapshot_dates, spam_rows
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        acb_rows_raw, prices, wallet_rows, tx_raw_rows, snapshot_dates, spam_rows = await run_in_threadpool(_query, conn)
    finally:
        pool.putconn(conn)

    # Decrypt wallets
    wallets_by_id = {}
    for wid, account_id_raw, w_chain, label in wallet_rows:
        account_id = _dec_str(account_id_raw) if isinstance(account_id_raw, (bytes, memoryview)) else (str(account_id_raw) if account_id_raw else "")
        wallets_by_id[wid] = {
            "id": wid,
            "address": account_id,
            "chain": (w_chain or "").lower(),
            "label": label or "",
        }

    # Decrypt spam rules (user-scoped)
    spam_tokens: set = set()
    for rt_raw, val_raw in spam_rows:
        rt = _dec_str(rt_raw)
        val = _dec_str(val_raw)
        if rt == "token_symbol" and val:
            spam_tokens.add(val)

    # D-07: Aggregate wallet balances from raw transaction rows after decryption
    from collections import defaultdict as _defaultdict
    wallet_token_in: dict = _defaultdict(lambda: _defaultdict(Decimal))
    wallet_token_out: dict = _defaultdict(lambda: _defaultdict(Decimal))
    wallet_token_fee: dict = _defaultdict(lambda: _defaultdict(Decimal))
    wallet_chain: dict = {}  # wallet_id -> chain string

    chain_divisors = {
        "near": Decimal("1" + "0" * 24),
        "ethereum": Decimal("1" + "0" * 18),
        "polygon": Decimal("1" + "0" * 18),
        "optimism": Decimal("1" + "0" * 18),
        "cronos": Decimal("1" + "0" * 18),
    }

    for wid, t_chain, direction_raw, amount_raw, fee_raw, token_id_raw in tx_raw_rows:
        direction = _dec_str(direction_raw)
        amount_str = _dec_str(amount_raw)
        fee_str = _dec_str(fee_raw)
        token_id = _dec_str(token_id_raw)

        if not amount_str:
            continue
        try:
            amount_dec = Decimal(amount_str)
        except Exception:
            continue

        wallet_chain[wid] = t_chain or "near"

        # Native token (token_id IS NULL) or FT token
        if token_id is None:
            # Native balance tracking per wallet
            token_key = "NEAR" if (t_chain or "near").lower() == "near" else "ETH"
            if direction == "in":
                wallet_token_in[token_key][wid] += amount_dec
            elif direction == "out":
                wallet_token_out[token_key][wid] += amount_dec
                if fee_str:
                    try:
                        wallet_token_fee[token_key][wid] += Decimal(fee_str)
                    except Exception:
                        pass

    # Build wallet_token_balances from native tx replay
    wallet_token_balances: dict[str, dict[int, float]] = {}
    for token_key in set(list(wallet_token_in.keys()) + list(wallet_token_out.keys())):
        for wid in set(list(wallet_token_in[token_key].keys()) + list(wallet_token_out[token_key].keys())):
            t_chain = wallet_chain.get(wid, "near")
            divisor = chain_divisors.get(t_chain, Decimal("1" + "0" * 24))
            bal_in = wallet_token_in[token_key][wid]
            bal_out = wallet_token_out[token_key][wid]
            bal_fee = wallet_token_fee[token_key].get(wid, Decimal(0))
            balance = float((bal_in - bal_out - bal_fee) / divisor)
            if balance > 0.000001:
                wallet_token_balances.setdefault(token_key, {})[wid] = balance

    # D-07: Decrypt ACB snapshot rows and find latest per token
    acb_by_token: dict = {}  # token_symbol -> (units_after, acb_per_unit_cad, total_cost_cad)
    for symbol_raw, units_raw, acb_raw, cost_raw, block_ts in acb_rows_raw:
        symbol = _dec_str(symbol_raw)
        if symbol is None:
            continue
        units_str = _dec_str(units_raw)
        acb_str = _dec_str(acb_raw)
        cost_str = _dec_str(cost_raw)
        # Since rows are ordered by block_timestamp DESC, first occurrence is latest
        if symbol not in acb_by_token:
            try:
                units = Decimal(units_str) if units_str else Decimal(0)
                acb_per = Decimal(acb_str) if acb_str else Decimal(0)
                total_cost = Decimal(cost_str) if cost_str else Decimal(0)
                acb_by_token[symbol] = (units, acb_per, total_cost)
            except Exception:
                pass

    acb_rows = [(sym, data[0], data[1], data[2]) for sym, data in acb_by_token.items()]

    # FT token list from tx_raw_rows (decrypt token_id)
    ft_token_set: set = set()
    for _, _, _, _, _, token_id_raw in tx_raw_rows:
        token_id = _dec_str(token_id_raw)
        if token_id:
            ft_token_set.add(token_id)

    ft_token_rows = [(t.upper(), t, None, None) for t in ft_token_set]

    # Symbol -> CoinGecko ID mapping for price lookups
    symbol_to_coin = {
        "NEAR": "near", "ETH": "ethereum", "MATIC": "matic-network",
        "CRO": "crypto-com-chain", "USDC": "usd-coin", "USDT": "tether",
        "DAI": "dai", "WETH": "ethereum", "WNEAR": "near",
        "SOL": "solana", "ALGO": "algorand", "GRT": "the-graph",
        "UNI": "uniswap", "MANA": "decentraland", "GTC": "gitcoin",
        "AKT": "akash-network", "SKL": "skale",
    }

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

    # Add FT tokens the user has interacted with (balance unknown until
    # on-chain query or ACB run, shown as 0 balance with token name visible)
    for row in ft_token_rows:
        token_symbol, token_id = row[0], row[1]
        token_name = row[2] if len(row) > 2 else None
        icon_url = row[3] if len(row) > 3 else None

        if token_symbol in acb_symbols:
            continue

        # Skip unresolved contract addresses (long hex or long .near names)
        if len(token_symbol) > 30:
            continue

        is_spam = token_symbol in spam_tokens
        if is_spam and not includeSpam:
            continue

        if asset and token_symbol != asset.upper():
            continue

        coin_id = symbol_to_coin.get(token_symbol, token_symbol.lower())
        price_usd = prices.get(coin_id, 0.0)

        # Include icon_url if it's a URL or data URI (SVG/PNG)
        clean_icon = icon_url if icon_url else None

        all_chains.add("near")
        all_asset_names.add(token_symbol)

        assets.append({
            "asset": token_symbol,
            "chain": "near",
            "chain_name": "NEAR",
            "balance": 0,
            "price_usd": price_usd,
            "value_usd": 0,
            "is_spam": is_spam,
            "wallets": [],
            "pending_balance": True,
            "token_name": token_name,
            "icon_url": clean_icon,
            "contract": token_id,
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
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """Mark a token as spam for this user.

    D-07: User-scoped spam rules use encrypted columns rule_type_enc and value_enc.
    """
    user_id = user["user_id"]
    token_symbol = body.get("token_symbol", "")
    reason = body.get("reason", "User marked")

    # Encrypt rule_type and value for user-scoped rule
    from db.crypto import EncryptedBytes
    rule_type_enc = EncryptedBytes().process_bind_param("token_symbol", None)
    value_enc = EncryptedBytes().process_bind_param(token_symbol, None)

    def _insert(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """INSERT INTO spam_rules (user_id, rule_type_enc, value_enc, created_by, is_active, created_at)
                   VALUES (%s, %s, %s, %s, TRUE, NOW())
                   ON CONFLICT DO NOTHING""",
                (user_id, rule_type_enc, value_enc, reason),
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
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(get_pool_dep),
):
    """Remove spam flag for a token.

    D-07: User-scoped spam rules use encrypted columns. We fetch all active rules,
    decrypt value_enc in Python, and disable the matching one.
    """
    user_id = user["user_id"]

    def _fetch_and_disable(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """SELECT id, rule_type_enc, value_enc FROM spam_rules
                   WHERE user_id = %s AND is_active = TRUE""",
                (user_id,),
            )
            rows = cur.fetchall()
            ids_to_disable = []
            for row_id, rt_raw, val_raw in rows:
                rt = _dec_str(rt_raw)
                val = _dec_str(val_raw)
                if rt == "token_symbol" and val == token_symbol:
                    ids_to_disable.append(row_id)

            if ids_to_disable:
                cur.execute(
                    "UPDATE spam_rules SET is_active = FALSE WHERE id = ANY(%s)",
                    (ids_to_disable,),
                )
                conn.commit()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        await run_in_threadpool(_fetch_and_disable, conn)
    finally:
        pool.putconn(conn)

    return {"ok": True}
