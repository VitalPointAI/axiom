# Phase 11: Robustness & Missing Features - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Harden fragile areas across the pipeline, establish a unified audit log for all data mutations, add data export validation with manifest checksums, implement multi-currency swap decomposition for arbitrary multi-hop routes, and add a read-only offline/cached mode for working without live APIs. This phase addresses all remaining unfixed concerns from CONCERNS.md.

</domain>

<decisions>
## Implementation Decisions

### Audit Log Consistency
- Track **all data mutations**: classification changes, ACB corrections, duplicate merges, manual balance overrides, report generation events, verification resolutions
- **Single unified audit table** with columns: entity_type, entity_id, action, old_value (JSONB), new_value (JSONB), user_id, timestamp
- **Migrate and deprecate** the existing `classification_audit_log` table into the new unified table via Alembic migration. Drop the old table after data migration
- Audit log **queryable via API + visible in UI**: FastAPI endpoint for audit history per entity, UI shows 'History' tab on transaction detail and verification detail views

### Data Export Validation
- **MANIFEST.json** generated alongside the tax package: lists every file with SHA-256 hash, generation timestamp, and source data version
- **Snapshot metadata** in manifest: last transaction timestamp, total transaction count, ACB snapshot version, needs_review count at generation time
- **Stale report detection**: compare current data fingerprint against manifest metadata. Show warning banner "Data has changed since this report was generated" with one-click re-generate button
- **Manifest included in downloads**: accountant receives a verifiable, self-contained package with MANIFEST.json alongside CSVs and PDFs

### Fragile Area Hardening
- **Both runtime invariant checks AND integration test coverage** across all four fragile areas
- **All four areas prioritized equally**: ACB calculation, transaction classifier, balance reconciliation, exchange integration
- **Violation handling**: flag + continue. Log violations to audit_log, set needs_review=True on affected records, continue processing. Pipeline never halts on invariant violation
- **ACB invariants**: pool balance consistency, no negative ACB without needs_review, fee adjustments match transaction fees
- **Classifier invariants**: every tx gets exactly one primary classification, multi-leg decomposition balances (sell + buy + fee legs sum correctly), no orphan legs
- **Reconciliation invariants**: reconciliation covers all wallets (no silent skips), diagnosis categories are complete, totals balance
- **Exchange invariants**: schema validation per exchange format, required fields present, amount/date parsing never silently returns zero

### Multi-Currency Swap Decomposition
- Handle **arbitrary multi-hop swaps** (A->B->C->D->...) not just two-hop
- Decompose into individual legs with proper cost basis tracking per intermediate token
- Covers all DeFi routing scenarios (DEX aggregators, multi-pool routes)

### Offline / Cached Mode
- **Read-only cached mode**: reports, verification, and UI work with existing DB data when APIs are unavailable
- Indexing operations gracefully skip/queue when offline — no crashes, no silent data loss
- No new data fetched in offline mode, but classification, ACB, verification, and reporting all function normally

### Claude's Discretion
- Unified audit table schema details (indexes, partitioning strategy)
- Invariant check placement and granularity
- Multi-hop swap detection algorithm (EVM log analysis, token transfer tracing)
- Offline mode detection mechanism (health check vs config flag vs automatic)
- Integration test scenario selection and coverage targets

</decisions>

<specifics>
## Specific Ideas

- Accountant should be able to see full change history on any transaction or verification item via the UI
- Manifest makes the tax package self-verifiable — accountant can confirm nothing was modified after generation
- "Flag + continue" pattern matches the existing oversell clamp approach in ACBPool (needs_review=True, keep processing)
- Multi-hop swap support addresses real DeFi usage patterns (1inch, Paraswap, etc. route through multiple pools)

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `classification_audit_log` table (migration 003): existing audit schema to migrate from
- `engine/classifier/` sub-package (split in Phase 10): modular structure ready for invariant injection
- `engine/acb/` sub-package (split in Phase 10): ACBPool.dispose() already has oversell clamp pattern
- `engine/evm_decoder.py`: 21 DeFi selectors, foundation for multi-hop detection
- `reports/generate.py`: PackageBuilder orchestrates all reports — add manifest generation here
- `verify/reconcile.py` + `verify/diagnosis.py`: already has auto-diagnosis categories
- `indexers/nearblocks_client.py`: already has retry + backoff — extend with offline detection

### Established Patterns
- `needs_review=True` flag on records requiring human attention (used across classifier, ACB, verification)
- Job queue pattern in `indexing_jobs` for async processing
- JSONB for flexible data storage (raw_data columns on transactions)
- `sanitize_for_log()` in config.py for sensitive data handling

### Integration Points
- `db/migrations/versions/` — new migration for unified audit table + classification_audit_log migration
- `api/routers/` — new audit history endpoint, stale report warning on reports endpoints
- `web/app/dashboard/` — History tab on transaction/verification detail views
- `reports/generate.py` — manifest generation in PackageBuilder
- `engine/classifier/`, `engine/acb/`, `verify/`, `indexers/exchange_parsers/` — invariant checks injected

</code_context>

<deferred>
## Deferred Ideas

- Digital signatures on report packages (key management complexity — future enhancement)
- Full offline cache layer with API response replay (v2)
- Real-time price updates via WebSocket
- Tax optimization suggestions

</deferred>

---

*Phase: 11-robustness-missing-features*
*Context gathered: 2026-03-14*
