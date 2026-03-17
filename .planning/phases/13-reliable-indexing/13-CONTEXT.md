# Phase 13: Reliable Indexing - Context

**Gathered:** 2026-03-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Investigate and implement the most reliable, cost-effective indexing solution for 100% transaction data coverage across all chains and wallets. Evaluate decentralized options (TheGraph, SubQuery) and dedicated cloud indexing. Implement near real-time continuous indexing with a path toward full self-hosted control. Research potential revenue-generating services from indexed data. The entire product depends on reliable, accurate data that stays up to date.

</domain>

<decisions>
## Implementation Decisions

### Indexing Architecture
- Hybrid approach: managed services as starting point, clear path toward self-hosted infrastructure
- NEAR Lake Framework as primary NEAR data source — streams blocks from S3, no rate limits, real-time
  - Cost optimization is critical — user previously found NEAR Lake more expensive than expected
  - Researcher must investigate cost-optimized patterns (targeted block ranges, local caching, efficient S3 reads)
- Multi-provider with failover for EVM chains (Alchemy, Infura, QuickNode) — upgrade to self-hosted node (Erigon/Reth) when usage justifies it
- Near real-time streaming for transaction updates — WebSocket/SSE subscriptions for new blocks
- Plugin registry with config for adding new chains — chain plugins registered via config/database, builds on existing chain_plugin.py ABC

### Data Coverage Strategy
- Must support ALL chains — including Bitcoin and any future chain the user adds
- Chain-native RPCs + custom parsers for all chains including those with poor API support (Akash via Cosmos SDK RPC, XRP Ledger API, Sweat via NEAR subnets, Bitcoin via Bitcoin Core RPC or Blockstream/Mempool.space API)
- Dual RPC strategy per chain: archival node access for historical transaction backfill + current/full node RPC for recent transactions and real-time streaming
- Continuous balance reconciliation for gap detection — after each sync, compare calculated vs on-chain balance, trigger targeted re-index on mismatch (extends Phase 5 BalanceReconciler pattern)
- Target data freshness: under 5 minutes from on-chain confirmation to visible in Axiom

### Revenue & Cost Model
- Monthly budget ceiling: $50-200/month for indexing infrastructure
- Research all potential revenue streams (no commitment to build):
  - Indexed data API / RPC access
  - Tax calculation as a service (expose classification + ACB engine)
  - Multi-chain webhook/notification service
- Built-in cost dashboard: track API calls, S3 reads, RPC requests per chain, monthly cost estimates in admin UI, budget threshold alerts

### Migration & Continuity
- Hard cutover with rollback — switch to new sources directly, keep old code available for rollback
- Single source per chain — one primary data source per chain, no permanent multi-source fallback
- Up to 24 hours downtime acceptable during planned migration maintenance
- Full re-index from new source — re-pull all historical data to validate new source and ensure data consistency

### Claude's Discretion
- Specific managed service providers to evaluate (TheGraph vs SubQuery vs Goldsky vs Moralis)
- NEAR Lake S3 optimization strategy (batch reads, block range targeting, caching layer)
- EVM provider selection and free tier optimization
- Cost dashboard implementation approach (admin page vs separate monitoring)
- Plugin hot-reload mechanism details
- Streaming connection management (reconnection, backpressure handling)

</decisions>

<specifics>
## Specific Ideas

- "Leaning towards full control via self-hosted indexer nodes, but cost and ops burden are important considerations" — the path to self-hosted matters more than starting there
- "Last time I tried to implement NEAR Lake it was far more than $5-20/month" — cost optimization for NEAR Lake is a critical research item
- "The entire product depends on reliable, accurate data that stays up to date" — reliability is non-negotiable
- Must support all chains, including Bitcoin — not just NEAR and EVM
- Consider archival node RPC for historical data + current node RPC for recent/real-time — dual strategy per chain
- Existing indexer service (service.py) uses FOR UPDATE SKIP LOCKED — already multi-worker ready, streaming should build on this foundation

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `indexers/service.py`: Job queue processor with handler dispatch, exponential backoff, graceful shutdown — core orchestration layer to extend
- `indexers/chain_plugin.py`: ChainFetcher ABC — plugin interface for new chain sources
- `indexers/near_fetcher.py`: NEAR transaction fetcher with NearBlocks — reference for NEAR Lake replacement
- `indexers/evm_fetcher.py`: Etherscan V2 + Alchemy fetcher — reference for multi-provider approach
- `indexers/price_service.py`: Multi-source price service with caching — reusable as-is
- `verify/reconcile.py`: BalanceReconciler with NEAR decomposed + EVM dual cross-check — gap detection foundation
- `indexers/neardata_indexer.py`, `indexers/neardata_fast.py`: Existing NEAR data stream experiments — may have useful patterns

### Established Patterns
- Job queue: PostgreSQL `indexing_jobs` with cursor-based resume, FOR UPDATE SKIP LOCKED
- Plugin dispatch: job_type-based handler registration in service.py
- Rate limiting: Adaptive delay based on API key presence (config.py)
- Multi-user isolation: user_id FK on all data tables
- Price caching: Shared price_cache table, token-agnostic
- Balance reconciliation: Dual verification (count check + balance reconciliation) after each sync

### Integration Points
- `indexers/service.py`: Register new chain fetchers and streaming handlers
- `config.py`: Add new environment variables for indexing service credentials
- `api/routers/`: Add cost dashboard and indexing status endpoints
- `docker-compose.prod.yml`: May need additional containers for streaming services
- `db/migrations/`: Schema changes for cost tracking, enhanced job queue

</code_context>

<deferred>
## Deferred Ideas

- Building revenue-generating services (indexed data API, tax-as-a-service, webhook service) — research only in this phase, build in future milestone
- Self-hosted archive nodes (NEAR, EVM) — evaluate in this phase, build when usage/revenue justifies
- No-code chain builder (admin UI to configure new chains) — future productization feature

</deferred>

---

*Phase: 13-reliable-indexing*
*Context gathered: 2026-03-17*
