# Phase 13: Reliable Indexing - Research

**Researched:** 2026-03-17
**Domain:** Multi-chain blockchain indexing — NEAR, EVM, XRP, Akash; managed services vs self-hosted; streaming; cost tracking
**Confidence:** HIGH (core NEAR/EVM stack), MEDIUM (cost model estimates), MEDIUM (Akash/XRP gap fill)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Hybrid approach**: managed services as starting point, clear path toward self-hosted infrastructure
- **NEAR Lake Framework** as primary NEAR data source — streams blocks from S3, no rate limits, real-time
  - Cost optimization is critical — user previously found NEAR Lake more expensive than expected
  - Researcher must investigate cost-optimized patterns (targeted block ranges, local caching, efficient S3 reads)
- **Multi-provider with failover for EVM chains** (Alchemy, Infura, QuickNode) — upgrade to self-hosted node (Erigon/Reth) when usage justifies it
- **Near real-time streaming** for transaction updates — WebSocket/SSE subscriptions for new blocks
- **Plugin registry with config** for adding new chains — chain plugins registered via config/database, builds on existing `chain_plugin.py` ABC
- **Chain-native RPCs + custom parsers** for all chains including poor API support chains (Akash via Cosmos SDK RPC, XRP Ledger API, Sweat via NEAR subnets)
- **Continuous balance reconciliation** for gap detection — after each sync, compare calculated vs on-chain balance, trigger targeted re-index on mismatch (extends Phase 5 BalanceReconciler pattern)
- **Target data freshness**: under 5 minutes from on-chain confirmation to visible in Axiom
- **Monthly budget ceiling**: $50–200/month for indexing infrastructure
- **Revenue stream research only** (no commitment to build): indexed data API, tax-as-a-service, webhook service
- **Built-in cost dashboard**: track API calls, S3 reads, RPC requests per chain, monthly cost estimates in admin UI, budget threshold alerts
- **Hard cutover with rollback** — switch to new sources directly, keep old code available for rollback
- **Single source per chain** — one primary data source per chain, no permanent multi-source fallback
- **Up to 24 hours downtime** acceptable during planned migration maintenance
- **Full re-index from new source** — re-pull all historical data to validate new source and ensure data consistency

### Claude's Discretion
- Specific managed service providers to evaluate (TheGraph vs SubQuery vs Goldsky vs Moralis)
- NEAR Lake S3 optimization strategy (batch reads, block range targeting, caching layer)
- EVM provider selection and free tier optimization
- Cost dashboard implementation approach (admin page vs separate monitoring)
- Plugin hot-reload mechanism details
- Streaming connection management (reconnection, backpressure handling)

### Deferred Ideas (OUT OF SCOPE)
- Building revenue-generating services (indexed data API, tax-as-a-service, webhook service) — research only in this phase, build in future milestone
- Self-hosted archive nodes (NEAR, EVM) — evaluate in this phase, build when usage/revenue justifies
- No-code chain builder (admin UI to configure new chains) — future productization feature
</user_constraints>

---

## Summary

Phase 13 replaces and upgrades the current NearBlocks-based NEAR fetcher and Etherscan EVM fetcher with a reliable multi-chain streaming architecture. The current system is request/response polling against rate-limited third-party APIs; the new system needs continuous block streaming with < 5 min latency, full historical coverage, gap detection, and cost visibility.

The key discovery is that **neardata.xyz (FastNEAR) is a free, no-auth HTTP API that supersedes the S3-based NEAR Lake Framework for most use cases**. It returns each block as a single JSON object at no cost. The S3 Lake Framework costs ~$30/month in GET/LIST requests at current NEAR block rates (~144,000 blocks/day). FastNEAR is the preferred NEAR data source and eliminates the "NEAR Lake more expensive than expected" problem. The existing `neardata_indexer.py` already uses it — the Phase 13 work is integrating that approach into the production `service.py` job queue and adding streaming.

For EVM, the existing Etherscan V2 fetcher handles historical sync adequately. Real-time streaming via WebSocket (`eth_subscribe newHeads`) requires a dedicated provider endpoint (Alchemy/QuickNode/Infura). Free tier limits (~30M Alchemy CUs/month or 100k requests/day on Infura) are sufficient for a small portfolio tracker. Provider failover should be sequential, not concurrent.

For gap detection, the existing `BalanceReconciler` (Phase 5) already has the hook — Phase 13 extends it with targeted re-index job queuing when mismatches are detected.

**Primary recommendation:** Use neardata.xyz for NEAR streaming (free), Alchemy free tier for EVM real-time with Etherscan for historical, PostgreSQL LISTEN/NOTIFY + SSE for frontend streaming, and a lightweight `api_cost_log` table for the cost dashboard.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `aiohttp` | 3.x | Async HTTP for neardata.xyz block streaming | Already used in `neardata_indexer.py`; handles 50 concurrent requests |
| `requests` | 2.x | Sync HTTP for EVM/XRP/Akash RPC calls | Already used in all fetchers; synchronous jobs fit the current service.py pattern |
| `psycopg2` | 2.9.x | PostgreSQL LISTEN/NOTIFY for streaming triggers | Already used; async notify is simplest pub/sub without Redis |
| `asyncio` | stdlib | Async event loop for near real-time block polling | Used in neardata_indexer.py; needed for streaming worker |
| FastAPI `StreamingResponse` | 0.115.x | SSE endpoint for frontend real-time updates | Already used for reports; same pattern |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `boto3` | 1.x | AWS S3 access for NEAR Lake Framework fallback | Only if neardata.xyz unavailable; NOT primary path |
| `near-lake-framework` | 0.x (PyPI) | S3-based NEAR block streaming | Fallback only — neardata.xyz preferred |
| `web3.py` | 7.x | EVM WebSocket subscriptions for `eth_subscribe` | Real-time new block detection on EVM chains |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| neardata.xyz (FastNEAR) | NEAR Lake Framework (S3) | S3 costs ~$30/month; neardata.xyz is free. Use neardata.xyz unless SLA guarantees are needed |
| Etherscan V2 historical | TheGraph subgraph | TheGraph Hosted Service deprecated 2026; decentralized network has GRT fees; overkill for a personal tax tool |
| Etherscan V2 historical | Goldsky Mirror | Goldsky is well-suited for high-volume dApps; pricing is contact-based; overkill for the budget |
| Etherscan V2 historical | SubQuery (NEAR + EVM) | SubQuery supports NEAR + EVM in one platform; TypeScript-native; overhead of running a node; better fit if scaling to many users |
| PostgreSQL LISTEN/NOTIFY | Redis pub/sub | Redis adds infra complexity; PostgreSQL already present; sufficient for single-server deployment |
| Alchemy WebSocket | QuickNode Streams | QuickNode Streams pricing migrated to API-credit model (Feb 2026); Ethereum mainnet stream = ~4.3M credits/month; costs add up quickly |

**Installation:**
```bash
pip install aiohttp requests psycopg2-binary boto3
# web3.py only if implementing EVM WebSocket streaming:
pip install web3
```

---

## Architecture Patterns

### Recommended Project Structure
```
indexers/
├── service.py              # Job queue dispatcher (existing — extend with streaming worker)
├── chain_plugin.py         # ChainFetcher ABC (existing)
├── near_stream_fetcher.py  # NEW: neardata.xyz streaming fetcher (replaces near_fetcher.py)
├── evm_stream_fetcher.py   # NEW: WebSocket-based EVM real-time + Etherscan historical
├── near_fetcher.py         # KEEP: NearBlocks fallback (do not delete for rollback)
├── evm_fetcher.py          # KEEP: Etherscan V2 historical (reuse as-is)
├── xrp_fetcher.py          # EXTEND: public XRPL RPC (already stubbed)
├── akash_fetcher.py        # EXTEND: Cosmos SDK LCD/RPC (already stubbed)
├── cost_tracker.py         # NEW: Lightweight API call counter, writes to api_cost_log
└── streaming_worker.py     # NEW: Long-running asyncio worker for near real-time updates
db/
└── migrations/
    └── 011_cost_tracking.sql  # NEW: api_cost_log table + chain_sync_config table
api/
└── routers/
    └── admin.py            # EXTEND: /admin/cost-dashboard and /admin/indexing-status endpoints
```

### Pattern 1: neardata.xyz Block Streaming (NEAR)

**What:** Poll `mainnet.neardata.xyz/v0/last_block/final` every 0.6s; fetch each new block at `/v0/block/{height}`; filter transactions for tracked wallets; upsert into transactions table.

**When to use:** All NEAR real-time indexing. Replaces NearBlocks for live updates.

**Key properties:**
- Free, no API key
- Bandwidth-limited to 1 Gbps (shared)
- Returns block as single JSON with `tx_hash` on every receipt — no additional RPC calls needed
- Latency: 0.1–2.1 seconds behind chain tip (documented)

```python
# Source: github.com/fastnear/neardata-server + neardata_indexer.py patterns
import asyncio
import aiohttp

NEARDATA_BASE = "https://mainnet.neardata.xyz"
POLL_INTERVAL = 0.6  # seconds (block time ~0.6s post May 2025 upgrade)

async def stream_near_blocks(wallets: set, on_tx_found):
    async with aiohttp.ClientSession() as session:
        last_block = await get_last_final_block(session)
        while True:
            current = await get_last_final_block(session)
            for height in range(last_block + 1, current + 1):
                block = await fetch_block(session, height)
                if block:
                    txs = extract_wallet_txs(block, wallets)
                    if txs:
                        await on_tx_found(txs)
            last_block = current
            await asyncio.sleep(POLL_INTERVAL)

async def fetch_block(session, height: int) -> dict | None:
    # Use /v0/block_opt for optimistic (lower latency); /v0/block for finalized
    async with session.get(f"{NEARDATA_BASE}/v0/block/{height}") as resp:
        if resp.status == 200:
            text = await resp.text()
            return json.loads(text) if text and text != 'null' else None
    return None
```

### Pattern 2: EVM Real-Time via WebSocket eth_subscribe

**What:** Use `eth_subscribe("newHeads")` on an Alchemy/Infura WebSocket endpoint to get notified of new blocks; then fetch full transactions for tracked wallets via Etherscan V2 (incremental, last N blocks).

**When to use:** EVM chains (ETH, Polygon, Cronos, Optimism). WebSocket only needed for the trigger; historical data still from Etherscan V2.

**Reconnection pattern** (critical — viem/ethers.js both have known reconnect issues):
```python
# Source: Alchemy docs + Chainstack guide — manual reconnect with exponential backoff
import asyncio, websockets, json

async def watch_evm_blocks(ws_url: str, on_new_head):
    backoff = 1
    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=20) as ws:
                await ws.send(json.dumps({
                    "id": 1, "jsonrpc": "2.0",
                    "method": "eth_subscribe", "params": ["newHeads"]
                }))
                backoff = 1  # reset on successful connect
                async for message in ws:
                    data = json.loads(message)
                    if "params" in data:
                        await on_new_head(data["params"]["result"])
        except (websockets.ConnectionClosed, OSError) as e:
            wait = min(backoff * 2, 60)
            logger.warning(f"WS disconnected: {e}. Reconnecting in {wait}s")
            await asyncio.sleep(wait)
            backoff = min(backoff * 2, 60)
```

### Pattern 3: PostgreSQL LISTEN/NOTIFY for Frontend SSE

**What:** When indexer inserts new transactions, it calls `NOTIFY new_transactions, '{"wallet_id": 42}'`. The FastAPI SSE endpoint LISTENs and pushes updates to the frontend.

**When to use:** Real-time wallet sync status updates; eliminates polling from frontend.

```python
# Source: psycopg2 docs + sse_server_postgres_listen_notify pattern
# In indexer (after upsert):
conn.execute("SELECT pg_notify('new_transactions', %s)", (json.dumps({"wallet_id": wallet_id}),))

# In FastAPI router:
from fastapi.responses import StreamingResponse
import psycopg2, select, json

async def stream_wallet_updates(wallet_id: int):
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(0)  # AUTOCOMMIT for LISTEN
    cur = conn.cursor()
    cur.execute("LISTEN new_transactions")
    async def event_generator():
        while True:
            if select.select([conn], [], [], 5.0)[0]:
                conn.poll()
                for notify in conn.notifies:
                    if json.loads(notify.payload).get("wallet_id") == wallet_id:
                        yield f"data: {notify.payload}\n\n"
                conn.notifies.clear()
            else:
                yield ": keepalive\n\n"  # SSE heartbeat
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### Pattern 4: Cost Tracking Middleware

**What:** Lightweight decorator/context manager that wraps every external API call, records chain, provider, call_type, response_time, and cost_estimate to `api_cost_log` table.

```python
# Source: LLM cost tracking patterns adapted for blockchain APIs
from contextlib import contextmanager
import time

class CostTracker:
    def __init__(self, pool):
        self.pool = pool

    @contextmanager
    def track(self, chain: str, provider: str, call_type: str, estimated_cost: float = 0.0):
        start = time.time()
        try:
            yield
        finally:
            elapsed = time.time() - start
            self._log(chain, provider, call_type, elapsed, estimated_cost)

    def _log(self, chain, provider, call_type, elapsed, cost):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO api_cost_log (chain, provider, call_type, response_ms, estimated_cost_usd)
                    VALUES (%s, %s, %s, %s, %s)
                """, (chain, provider, call_type, int(elapsed * 1000), cost))
            conn.commit()
        finally:
            self.pool.putconn(conn)
```

### Pattern 5: Chain Plugin Registry via DB Config

**What:** Store chain configuration in a `chain_sync_config` table. Service.py reads this at startup and registers the appropriate ChainFetcher subclass by `fetcher_class` name. Eliminates hardcoded handler dict.

```python
# chain_sync_config table row → handler registration
# fetcher_class: "NearStreamFetcher" | "EVMStreamFetcher" | "XRPFetcher" | "AkashFetcher"
# job_types: ["near_stream_sync", "near_historical_sync"]
# enabled: bool
# config_json: {"poll_interval": 0.6, "provider": "neardata.xyz"}
```

### Anti-Patterns to Avoid

- **Polling NearBlocks for real-time**: NearBlocks free tier allows only 6 req/min; ~10 blocks/min at 0.6s block time = immediate rate limit. Never use NearBlocks for streaming; use neardata.xyz.
- **Parallel S3 reads on NEAR Lake**: The user's bad experience was likely parallel concurrent GET requests. NEAR Lake is designed for sequential reads; batching strategies exist but neardata.xyz is simply better.
- **Permanent multi-source fallback**: Locked decision is single primary source per chain. Don't build logic that tries two sources concurrently; route to failover only on outage.
- **WebSocket without heartbeat/reconnect**: Both viem and ethers.js have documented reconnect gaps. Always implement manual reconnect with exponential backoff and ping interval.
- **Re-indexing without dedup**: Full re-index from new source will attempt to insert duplicates. The existing `ON CONFLICT DO NOTHING` upsert pattern handles this; ensure all new fetchers follow it.
- **Tracking blocks instead of wallet transactions**: The neardata.xyz approach scans all blocks and filters for wallets. This works but is compute-heavy for historical catch-up. For NearBlocks historical, wallet-centric API (`/v1/account/{id}/txns`) is faster. Use block scanning only for streaming; use wallet-centric APIs for historical backfill.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| NEAR block streaming | Custom S3 client iterating NEAR Lake buckets | neardata.xyz HTTP API (existing `neardata_indexer.py`) | Free, no auth, lower latency than S3, already prototyped |
| EVM block notifications | Polling Etherscan for new blocks | `eth_subscribe("newHeads")` via provider WebSocket | Push vs pull; Etherscan charges per request |
| PostgreSQL pub/sub | Redis queue | `pg_notify` / `LISTEN` | Already have PostgreSQL; no extra infra |
| API call cost tracking | External APM tool | Simple `api_cost_log` table + daily aggregation view | Budget is $50–200/month; Datadog/New Relic costs more than the indexing |
| XRPL transaction history | Full history rippled node (39 TB) | Public XRPL endpoints (`xrpl.org/cluster.altnet.rippletest.net`) or commercial APIs | Full history is 39 TB and grows 12 GB/day; public endpoints sufficient for wallet-level history |
| Cosmos SDK history | Custom Tendermint indexer | Cosmos LCD REST + pagination (`/cosmos/tx/v1beta1/txs?events=`) | Standard for all Cosmos chains; Akash public RPCs available |

**Key insight:** neardata.xyz eliminates the NEAR Lake cost problem entirely. The "NEAR data is expensive" experience was specifically about S3 GET/LIST billing. neardata.xyz is an HTTP cache in front of that S3 bucket, provided free by FastNEAR. The historical limitation is that sequential requests to neardata.xyz for old blocks can be slow; the solution is using NearBlocks historical API for catch-up and neardata.xyz for real-time only.

---

## Common Pitfalls

### Pitfall 1: NEAR Block Scanning vs. Wallet-Centric APIs

**What goes wrong:** Using neardata.xyz block scanner for historical backfill (e.g., 6+ months of blocks) takes days because NEAR produces ~144,000 blocks/day at old 1.2s rate; now ~144,000 × 0.6/1.2 = ~240,000+ blocks/day at 0.6s block time. Historical backfill of all blocks is impractical for initial sync.

**Why it happens:** Block scanning is designed for real-time; NearBlocks wallet-centric API (`/v1/account/{id}/txns`) is designed for historical.

**How to avoid:** Two-phase NEAR strategy:
1. **Historical catch-up**: Use NearBlocks API (paginated wallet transactions) up to latest indexed block. This is what `near_fetcher.py` already does.
2. **Real-time streaming**: Switch to neardata.xyz block polling after historical sync completes. Record cursor = last_block_processed in `indexing_jobs`.

**Warning signs:** Streaming worker is behind by more than 1000 blocks; catching up takes > 1 hour.

### Pitfall 2: NEAR Lake S3 Cost Spike

**What goes wrong:** NEAR Lake Framework using `near-lake-framework` Python library with high parallelism issues excessive GET requests: ~10 GET + LIST requests per block × 144,000 blocks/day = 1.44M requests/day. At $0.004/1000 LIST + $0.0004/1000 GET, monthly cost is ~$30/month in requests alone.

**Why it happens:** NEAR Lake fetches each shard separately (multiple GET requests per block); LIST operations are more expensive than GET.

**How to avoid:** Use neardata.xyz instead — it serves the full block as one JSON object, no S3 charges. Only fall back to NEAR Lake if neardata.xyz has a sustained outage (rare; maintained by FastNEAR team).

**Warning signs:** AWS bill exceeds $5/month for S3; `near-lake-framework` logs show high shard count.

### Pitfall 3: EVM WebSocket Connection Silently Drops

**What goes wrong:** `eth_subscribe` WebSocket connection drops (provider timeout, network blip) and the indexer stops receiving new blocks silently — no error raised, just no new events.

**Why it happens:** WebSocket connections timeout after inactivity; some providers drop connections after 5–10 minutes idle.

**How to avoid:** Implement ping interval (20 seconds) + watchdog timer: if no event received in 60 seconds, assume connection is dead, reconnect. Do not rely on the websockets library's built-in reconnect.

**Warning signs:** `last_indexed_block` timestamp not updated in > 2 minutes.

### Pitfall 4: NearBlocks Rate Limits During Historical Re-index

**What goes wrong:** Full re-index from NearBlocks for a wallet with 23,000+ transactions will hit the 6 req/min free tier limit immediately. With a paid key (190 req/min on Startup plan), a 500,000-call monthly limit is consumed in ~2,600 minutes = ~1.8 days.

**Why it happens:** Each paginated page = 1 API call. At 25 txns/page, 23,000 txns = 920 pages = 920 API calls per wallet.

**How to avoid:** For initial re-index, NearBlocks paid tier (Startup $67/month) is adequate. After historical sync, neardata.xyz handles real-time for free. NearBlocks key should be in env var `NEARBLOCKS_API_KEY` (already done in config.py). Budget: $67/month for NearBlocks Startup during re-index phase only; then downgrade or cancel.

**Warning signs:** 429 responses in indexer logs; `RATE_LIMIT_DELAY` is 3.0+ seconds.

### Pitfall 5: Etherscan Free Tier Exhaustion During Re-index

**What goes wrong:** Etherscan free tier provides limited daily requests. Full re-index of 4 EVM chains for multiple wallets can exhaust the daily quota.

**Why it happens:** Etherscan V2 endpoint uses a single API key across all chains; pagination at 10,000 tx/page minimizes calls, but large accounts still need many pages.

**How to avoid:** The existing `ETHERSCAN_API_KEY` pattern in config.py is correct. Use a single Etherscan V2 key. For re-index window, register one key per account on Etherscan (free). After re-index, incremental syncs are minimal (only new blocks since last cursor).

### Pitfall 6: Gap Detection Triggers Infinite Re-index Loop

**What goes wrong:** BalanceReconciler detects mismatch → queues re-index job → re-index finds same transactions → reconciler still shows mismatch (due to unclassified tx or price gap) → queues another re-index.

**Why it happens:** Balance mismatch can be caused by classification errors, fee calculation errors, or unindexed token events — not missing transactions.

**How to avoid:** Cap re-index retries at 3 per wallet per day. After 3 retries without fixing the mismatch, flag as `manual_review_required` in `account_verification_status`. Do not loop infinitely.

---

## Cost Analysis

### NEAR Data Sources

| Source | Monthly Cost | Rate Limits | Best For |
|--------|-------------|-------------|---------|
| neardata.xyz (FastNEAR) | **$0** (free) | 1 Gbps shared bandwidth | Real-time streaming (< 5 min freshness) |
| NEAR Lake Framework (S3) | **~$30/month** | None (pay per request) | Not recommended — neardata.xyz is better |
| NearBlocks Free | **$0** | 6 req/min, 10k/month | Development only |
| NearBlocks Startup | **$67/month** | 190 req/min, 500k/month | Historical re-index only |
| NearBlocks Standard | **$254/month** | 500 req/min, 3.75M/month | Production with heavy usage |

### EVM Data Sources

| Source | Monthly Cost | Rate Limits | Best For |
|--------|-------------|-------------|---------|
| Etherscan V2 Free | **$0** | ~5 req/sec | Historical backfill (existing) |
| Alchemy Free | **$0** | 30M CUs/month | EVM WebSocket streaming |
| Infura Free | **$0** | 100k req/day | EVM WebSocket fallback |
| QuickNode Free | **$0** | 100k req/day | Alternative free WebSocket |
| Erigon/Reth self-hosted | **~$100–200/month VPS** | Unlimited | When EVM usage justifies (1.77TB disk for Ethereum archive) |

### Recommended Budget Allocation (within $50–200/month ceiling)

- **Phase 13 initial re-index window**: NearBlocks Startup ($67/month) for 1–2 months during historical sync, then evaluate downgrade
- **Ongoing production**: neardata.xyz ($0) + Alchemy free ($0) + Etherscan free ($0) = **$0–$67/month**
- **If NearBlocks free tier sufficient** (6 wallets, slow sync acceptable): **$0/month**

---

## Code Examples

### NEAR Historical Sync (NearBlocks wallet-centric — already in near_fetcher.py)
```python
# Source: nearblocks.io/apis + existing near_fetcher.py
# Keep using NearBlocks for historical catch-up; switch to neardata.xyz for streaming
GET /v1/account/{account_id}/txns?limit=25&cursor={cursor}&order=asc
```

### neardata.xyz Block Fetch (from neardata_indexer.py — production-ready)
```python
# Source: github.com/fastnear/neardata-server
async with session.get(f"https://mainnet.neardata.xyz/v0/block/{height}") as resp:
    # Returns full block + receipts as single JSON; tx_hash on every receipt
    # Returns "null" if block doesn't exist (skip it)
    if resp.status == 200:
        data = await resp.json()
```

### PostgreSQL Schema for Cost Tracking
```sql
-- Migration 011
CREATE TABLE api_cost_log (
    id          BIGSERIAL PRIMARY KEY,
    logged_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    chain       TEXT NOT NULL,           -- 'near', 'ethereum', 'polygon', etc.
    provider    TEXT NOT NULL,           -- 'neardata_xyz', 'nearblocks', 'etherscan', 'alchemy'
    call_type   TEXT NOT NULL,           -- 'block_fetch', 'wallet_txns', 'balance_check', etc.
    response_ms INT,
    estimated_cost_usd NUMERIC(12, 8) DEFAULT 0
);

CREATE INDEX ix_api_cost_log_chain_date ON api_cost_log (chain, logged_at DESC);

-- Monthly summary view
CREATE VIEW api_cost_monthly AS
SELECT
    chain,
    provider,
    call_type,
    date_trunc('month', logged_at) AS month,
    COUNT(*) AS call_count,
    SUM(estimated_cost_usd) AS total_cost_usd
FROM api_cost_log
GROUP BY 1, 2, 3, 4;

-- Chain sync config (plugin registry)
CREATE TABLE chain_sync_config (
    chain           TEXT PRIMARY KEY,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    fetcher_class   TEXT NOT NULL,       -- 'NearStreamFetcher', 'EVMStreamFetcher', etc.
    job_types       TEXT[] NOT NULL,     -- job types this chain handles
    config_json     JSONB NOT NULL DEFAULT '{}',
    monthly_budget_usd NUMERIC(8,2),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Cosmos SDK (Akash) Transaction History
```python
# Source: Cosmos LCD REST API standard
# Akash public RPC: https://api.akash.network/cosmos/tx/v1beta1/txs
# Filter by address events
GET /cosmos/tx/v1beta1/txs?events=message.sender%3D%27{address}%27&pagination.limit=100&pagination.offset={offset}
GET /cosmos/tx/v1beta1/txs?events=transfer.recipient%3D%27{address}%27&pagination.limit=100&pagination.offset={offset}
# Must fetch both sender and recipient events; combine and deduplicate
```

### XRP Ledger Transaction History (extending existing stub)
```python
# Source: xrpl.org/build/websocket-tool
# Existing xrp_fetcher.py uses account_tx method correctly
# Key: use `limit: 200, ledger_index_min: -1` for full history pagination
# Public endpoints already in XRPL_ENDPOINTS list in xrp_fetcher.py
```

---

## Self-Hosted Node Evaluation (Deferred but researched)

| Node | Disk | RAM | Monthly VPS Cost | Notes |
|------|------|-----|-----------------|-------|
| Erigon 3 (Ethereum archive) | 1.77 TB NVMe | 32 GB+ | $150–300/month | Set `--prune.mode=archive`; defaults to full node in Erigon 3 |
| Reth (Ethereum archive) | ~2 TB NVMe | 16 GB+ | $150–300/month | Faster sync than Erigon; Rust-based |
| NEAR archival node | ~3+ TB | 32 GB+ | $200–400/month | Complex to operate; neardata.xyz makes this unnecessary |
| Clio (XRPL) | Requires rippled + Cassandra | 32 GB+ | $200–500/month | 4x more space-efficient than rippled; still 39 TB for full history |

**Recommendation:** Self-hosted EVM nodes are not justified at the current scale. The threshold is when monthly provider costs exceed $150–200/month or when uptime requirements exceed free tier SLAs.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| NEAR Lake Framework (S3) | neardata.xyz HTTP API (free) | 2023 (FastNEAR) | Eliminates ~$30/month S3 cost |
| NEAR block time 1.2s | 600ms blocks, 1.2s finality | May 2025 | Double the blocks/day; neardata.xyz poll interval should be 0.6s |
| TheGraph Hosted Service | Deprecated — use The Graph Network or migrate | 2026 | GRT fees apply on decentralized network; not recommended for private apps |
| Etherscan V1 per-chain APIs | Etherscan V2 unified (`chainid` param) | 2024 | One API key for all EVM chains (already in use) |
| NearBlocks as NEAR indexer | NearBlocks as historical only + neardata.xyz for real-time | Phase 13 target | Removes rate limit bottleneck from real-time path |
| QuickNode legacy GB billing | API credit model (Feb 1, 2026) | Feb 2026 | Ethereum stream ~4.3M credits/month at 20x multiplier; verify cost before adopting |

**Deprecated/outdated:**
- NEAR Indexer Framework: Requires running a NEAR full node; superseded by Lake Framework and neardata.xyz
- `neardata_indexer.py` (SQLite-based): Uses old SQLite schema; patterns are reusable but needs PostgreSQL port
- `neardata_fast.py` (SQLite-based): Same issue; good reference for batch processing patterns

---

## Managed Service Evaluation (Claude's Discretion)

### For NEAR

**Verdict: neardata.xyz is the winner**. Free, no auth, battle-tested by FastNEAR, already prototyped in `neardata_indexer.py`. No managed service adds value over this for a personal tax tool.

### For EVM

**Verdict: Etherscan V2 (historical) + Alchemy free WebSocket (real-time)**. Alchemy offers 30M CUs/month free; Ethereum `eth_subscribe newHeads` uses minimal CUs. Infura as secondary fallback (100k req/day free).

**Not recommended:**
- **Goldsky**: Contact-based pricing, designed for high-volume dApps; overkill for budget
- **SubQuery**: Good NEAR + EVM support; TypeScript-native; overhead of managing a SubQuery node; better for multi-user SaaS scaling
- **TheGraph**: Deprecated hosted service; decentralized network adds GRT token complexity; not cost-effective for private use
- **Moralis**: EVM-focused, free tier ~40k CUs/day; no NEAR support; adds API key management complexity without significant benefit over Alchemy + Etherscan

### For XRP
Use public XRPL cluster endpoints (already in `xrp_fetcher.py`). No managed service needed.

### For Akash
Use community-maintained RPC endpoints from Cosmos chain registry. No managed service needed.

---

## Revenue Stream Research (Deferred — research only)

| Service | Technical Feasibility | Estimated Revenue | Build Complexity |
|---------|----------------------|-------------------|-----------------|
| Indexed data API | HIGH — existing PostgreSQL schema could be exposed | $10–50/user/month | Medium — rate limiting, auth |
| Tax calculation API | HIGH — ClassifierHandler + ACBHandler already exist | $20–100/user/month | Low — wrap existing pipeline |
| Multi-chain webhook | MEDIUM — SSE/WebSocket streaming architecture being built | $5–20/user/month | Medium — webhook delivery queue |

These services would require Phase 14+ work. The indexing infrastructure built in Phase 13 (streaming, cost tracking, plugin registry) directly enables them.

---

## Open Questions

1. **neardata.xyz SLA and reliability**
   - What we know: Free service, 1 Gbps bandwidth limit, maintained by FastNEAR, open source
   - What's unclear: What happens if FastNEAR discontinues the service? No SLA published.
   - Recommendation: Keep NEAR Lake Framework code available as a fallback. The locked decision (hard cutover with rollback) handles this: keep `near_fetcher.py` for rollback.

2. **NEAR 600ms block time impact on streaming worker**
   - What we know: NEAR upgraded to 600ms blocks in May 2025; neardata.xyz serves both final and optimistic blocks
   - What's unclear: Whether neardata.xyz 1 Gbps limit causes throttling at 600ms poll intervals for multiple concurrent workers
   - Recommendation: Use `/v0/block_opt` (optimistic) for lower latency; fall back to `/v0/block` (final) on errors. Implement exponential backoff on 429 responses.

3. **Sweat (NEAR subnet) transaction access**
   - What we know: Sweat Economy runs on a NEAR subnet ("Sweat Wallet" chain); locked decision notes "Sweat via NEAR subnets"
   - What's unclear: Whether neardata.xyz covers NEAR subnet data or only mainnet
   - Recommendation: Research Sweat-specific API in Phase 13 wave 1; may require `api.sweateconomy.com` or a separate NEAR Lake instance for the Sweat subnet.

4. **Akash historical transaction depth**
   - What we know: Akash upgraded to Cosmos SDK v0.53 on Oct 28, 2025 (block #23939793); Cosmos RPC standard applies
   - What's unclear: Whether public Akash RPCs retain full history or prune old blocks; Cosmos chains commonly prune to last 1000 blocks on public nodes
   - Recommendation: Test public Akash RPC endpoints for historical depth. If pruned, use Mintscan API or Numia data service as fallback.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing, `tests/` directory) |
| Config file | `pytest.ini` or `pyproject.toml [tool.pytest]` — check existing |
| Quick run command | `pytest tests/test_indexers.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Behavior | Test Type | Automated Command |
|----------|-----------|-------------------|
| neardata.xyz block fetch extracts correct wallet transactions | unit (mock HTTP) | `pytest tests/test_near_stream_fetcher.py -x` |
| EVM WebSocket reconnect on connection drop | unit (mock websocket) | `pytest tests/test_evm_stream_fetcher.py::test_reconnect -x` |
| Cost tracker writes to api_cost_log correctly | unit | `pytest tests/test_cost_tracker.py -x` |
| chain_sync_config registry loads correct fetcher class | unit | `pytest tests/test_chain_registry.py -x` |
| Balance mismatch triggers re-index job (not infinite loop) | integration | `pytest tests/test_gap_detection.py -x` |
| Migration 011 creates api_cost_log and chain_sync_config tables | integration | `pytest tests/test_migrations.py::test_011 -x` |
| SSE endpoint sends event on pg_notify | integration | `pytest tests/test_streaming_api.py -x` |

### Wave 0 Gaps

- [ ] `tests/test_near_stream_fetcher.py` — covers neardata.xyz block extraction
- [ ] `tests/test_evm_stream_fetcher.py` — covers WebSocket reconnect + historical sync
- [ ] `tests/test_cost_tracker.py` — covers api_cost_log writes
- [ ] `tests/test_chain_registry.py` — covers plugin registry DB config
- [ ] `db/migrations/011_cost_tracking.sql` — new migration file
- [ ] Framework: existing pytest sufficient, no new installation needed

---

## Sources

### Primary (HIGH confidence)
- FastNEAR neardata-server GitHub: github.com/fastnear/neardata-server — API endpoints, free tier, bandwidth limits
- NEAR Documentation (neardata.xyz): docs.near.org/data-infrastructure/lake-framework/near-lake-framework — S3 cost breakdown ($17.20 GET + $21.60 LIST = $30.16/month)
- NearBlocks API pricing: nearblocks.io/apis — tier pricing (Free: 6 req/min; Startup: $67/month, 190 req/min)
- Existing `neardata_indexer.py` and `neardata_fast.py` — battle-tested neardata.xyz integration patterns
- Existing `service.py`, `chain_plugin.py`, `evm_fetcher.py` — established patterns to extend

### Secondary (MEDIUM confidence)
- WebSearch: EVM WebSocket reconnect patterns (viem issue #877, Alchemy docs) — reconnect not automatic; manual logic required
- WebSearch: Goldsky pricing — contact-based, Starter/Scale/Enterprise tiers; no published $/month rates confirmed
- WebSearch: SubQuery NEAR support — confirmed; TypeScript-native; $0.12/deployment-hour per additional network (2023 pricing, may have changed)
- WebSearch: Alchemy free tier — 30M CUs/month, 40 RPM on free plan
- WebSearch: Infura/QuickNode free tiers — 100k req/day each

### Tertiary (LOW confidence — flag for validation)
- Erigon 3 archive node disk = 1.77 TB (September 2025 measurement; growing ~12 GB/day)
- XRPL full history = 39 TB (January 2026 figure)
- NEAR block time now 0.6s (confirmed in NEAR blog post May 2025)
- Akash public RPC historical depth — unverified; assume pruned to recent blocks on public nodes

---

## Goldsky Mirror/Sink Evaluation (2026-03-21)

**Evaluated at user request** — deeper dive into Goldsky Mirror (managed blockchain data pipelines) and Sink (PostgreSQL direct-write connector).

### What Goldsky Mirror Does
Streams decoded on-chain data (blocks, transactions, logs, traces) directly into your database via managed pipelines. You define a YAML config specifying source chain + data types + destination, run `goldsky pipeline create`, and data flows into your PostgreSQL tables automatically. Handles backfill + real-time with upsert semantics for reorg handling.

### Chain Support
- **Supported:** NEAR (early adopter), Ethereum, Polygon, Optimism, Arbitrum, Base, and 40+ EVM chains
- **Not supported:** XRP Ledger, Akash/Cosmos SDK — still requires custom fetchers

### Pricing (as of May 2025)
- **Contact-sales / custom quote** for Mirror pipelines — no transparent self-serve pricing
- Free tier is primarily for hosted subgraphs, not Mirror/Sink pipelines
- Estimated minimum: **$200-500+/month** for multi-chain pipelines
- Axiom budget ceiling: $50-200/month — **does not fit**

### Comparison to Current Axiom Stack

| Dimension | Axiom Stack (Phase 13) | Goldsky Mirror |
|-----------|----------------------|----------------|
| NEAR real-time | neardata.xyz polling ($0) | Pipeline ($$$) |
| EVM real-time | Alchemy WebSocket ($0) | Pipeline ($$$) |
| EVM historical | Etherscan V2 ($0) | Included |
| XRP/Akash | Chain-native RPCs ($0) | Not supported |
| Setup | Custom code (~1000 LOC) | YAML + CLI (30 min) |
| Monthly cost | $0-67 | $200-500+ |
| Latency | < 5 min | Seconds |

### Decision: NOT ADOPTED
1. **Budget mismatch** — minimum cost exceeds budget ceiling
2. **Incomplete coverage** — XRP + Akash still need custom code
3. **Already built** — Phase 13 fetchers operational with 88 tests passing
4. **Overkill** — designed for high-volume dApps, not small portfolio trackers

### When to Revisit
- If Axiom scales to revenue-generating services (indexed data API, tax-as-a-service)
- If monthly indexing budget grows to $500+/month
- If Goldsky introduces transparent self-serve pricing with a viable free tier
- Check `goldsky.com/pricing` periodically

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified against existing codebase and official neardata.xyz docs
- Architecture: HIGH — based on existing `neardata_indexer.py` patterns + PostgreSQL LISTEN/NOTIFY well-documented
- Cost model: MEDIUM — NearBlocks pricing verified directly; Alchemy/Infura from WebSearch cross-referenced
- Pitfalls: HIGH — several from direct codebase analysis (rate limit config, NearBlocks 6 req/min already in config.py)
- Self-hosted node requirements: MEDIUM — from 2025 sources but disk size grows constantly

**Research date:** 2026-03-17
**Valid until:** 2026-04-17 (30 days — stable providers, but free tier limits can change)
