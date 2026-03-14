# Stub Implementations

This document lists all stub or unvalidated implementations in the Axiom codebase.
Each entry includes status, what works, what is missing, and the migration path.

---

## indexers/xrp_fetcher.py

**Status:** Functional stub — untested against live XRPL API

**What works:**
- Transaction parsing logic handles Payment, Escrow, Offer, TrustSet message types
- Direction determination (in/out/self) based on tx.Account and tx.Destination
- Amount parsing for native XRP (drops) and issued currencies
- Ripple epoch → Unix epoch timestamp conversion
- Pagination via XRPL `marker` field
- Endpoint rotation with retry logic (MAX_RETRIES=3)
- ON CONFLICT upsert into `transactions` table

**What is missing:**
- No validation against a real XRPL account with known transaction history
- Trust line token balances in `get_balance()` are not yet implemented (returns empty `tokens: []`)
- No integration tests with mocked HTTP responses

**Warning on init:**
```
WARNING:indexers.xrp_fetcher:XRPFetcher is a STUB implementation — untested against live XRPL API
```

**Migration path:**
1. Set up a test XRP account with a small known transaction history
2. Run `XRPFetcher.sync_wallet()` against it and compare DB output to XRPL explorer
3. Fix any parsing discrepancies found
4. Add integration tests with `responses` library mocking the XRPL JSON-RPC endpoints
5. Remove this stub designation once validated

---

## indexers/akash_fetcher.py

**Status:** Functional stub — untested against live Akash LCD API

**What works:**
- Transaction parsing for MsgSend, MsgDelegate, MsgUndelegate, MsgWithdrawDelegatorReward, MsgCreate/CloseDeployment
- Direction determination (in/out/self) based on Cosmos message types
- Sent and received tx search via Cosmos LCD `/cosmos/tx/v1beta1/txs`
- Pagination via `pagination.next_key`
- Endpoint rotation with retry logic (MAX_RETRIES=3)
- ON CONFLICT upsert into `transactions` table

**What is missing:**
- No validation against a real Akash account with known transaction history
- IBC token transfers not fully parsed (only native AKT via `uakt` denom)
- No integration tests with mocked HTTP responses

**Warning on init:**
```
WARNING:indexers.akash_fetcher:AkashFetcher is a STUB implementation — untested against live Akash LCD API
```

**Migration path:**
1. Set up a test Akash address with a small known transaction history
2. Run `AkashFetcher.sync_wallet()` against it and compare DB output to Akash explorer
3. Fix any parsing discrepancies found
4. Add integration tests with `responses` library mocking the Cosmos LCD endpoints
5. Remove this stub designation once validated

---

## GET /api/portfolio (root endpoint)

**Status:** Explicit 501 stub — returns "not yet implemented"

**What works:**
- Authentication enforcement (unauthenticated callers receive 401)

**What is missing:**
- Root portfolio endpoint body (summary is available at `/api/portfolio/summary`)
- This endpoint was created as an auth guard for test infrastructure

**OpenAPI description:** "Not yet implemented. Returns 501. Use /api/portfolio/summary for holdings and staking positions."

**Migration path:**
- Implement or redirect to `/api/portfolio/summary` once root portfolio behaviour is defined
- Or document that the root endpoint intentionally returns 501 and test expectations are correct

---

## indexers/coinbase_pro_indexer.py

**Status:** DEPRECATED — superseded by `indexers/exchange_parsers/coinbase.py`

**Emits:** `DeprecationWarning` on import:
```
coinbase_pro_indexer.py is deprecated. Use indexers/exchange_parsers/coinbase.py
for Coinbase CSV imports. Will be removed in v2.
```

**Migration path:**
- Use `indexers/exchange_parsers/coinbase.py` (`CoinbaseParser`) for all Coinbase data imports
- `CoinbaseParser` integrates with the PostgreSQL-backed `import_to_db` pipeline
- `coinbase_pro_indexer.py` will be removed in v2
