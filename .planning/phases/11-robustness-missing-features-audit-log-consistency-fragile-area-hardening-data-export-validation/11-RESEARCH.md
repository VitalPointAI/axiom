# Phase 11: Robustness & Missing Features - Research

**Researched:** 2026-03-14
**Domain:** Python/PostgreSQL — audit logging, data integrity, DeFi routing, offline modes
**Confidence:** HIGH (project codebase is the primary source; all patterns verified directly)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Audit Log Consistency**
- Track all data mutations: classification changes, ACB corrections, duplicate merges, manual balance overrides, report generation events, verification resolutions
- Single unified audit table with columns: entity_type, entity_id, action, old_value (JSONB), new_value (JSONB), user_id, timestamp
- Migrate and deprecate the existing `classification_audit_log` table into the new unified table via Alembic migration. Drop the old table after data migration
- Audit log queryable via API + visible in UI: FastAPI endpoint for audit history per entity, UI shows 'History' tab on transaction detail and verification detail views

**Data Export Validation**
- MANIFEST.json generated alongside the tax package: lists every file with SHA-256 hash, generation timestamp, and source data version
- Snapshot metadata in manifest: last transaction timestamp, total transaction count, ACB snapshot version, needs_review count at generation time
- Stale report detection: compare current data fingerprint against manifest metadata. Show warning banner "Data has changed since this report was generated" with one-click re-generate button
- Manifest included in downloads: accountant receives a verifiable, self-contained package with MANIFEST.json alongside CSVs and PDFs

**Fragile Area Hardening**
- Both runtime invariant checks AND integration test coverage across all four fragile areas
- All four areas prioritized equally: ACB calculation, transaction classifier, balance reconciliation, exchange integration
- Violation handling: flag + continue. Log violations to audit_log, set needs_review=True on affected records, continue processing. Pipeline never halts on invariant violation
- ACB invariants: pool balance consistency, no negative ACB without needs_review, fee adjustments match transaction fees
- Classifier invariants: every tx gets exactly one primary classification, multi-leg decomposition balances (sell + buy + fee legs sum correctly), no orphan legs
- Reconciliation invariants: reconciliation covers all wallets (no silent skips), diagnosis categories are complete, totals balance
- Exchange invariants: schema validation per exchange format, required fields present, amount/date parsing never silently returns zero

**Multi-Currency Swap Decomposition**
- Handle arbitrary multi-hop swaps (A->B->C->D->...) not just two-hop
- Decompose into individual legs with proper cost basis tracking per intermediate token
- Covers all DeFi routing scenarios (DEX aggregators, multi-pool routes)

**Offline / Cached Mode**
- Read-only cached mode: reports, verification, and UI work with existing DB data when APIs are unavailable
- Indexing operations gracefully skip/queue when offline — no crashes, no silent data loss
- No new data fetched in offline mode, but classification, ACB, verification, and reporting all function normally

### Claude's Discretion
- Unified audit table schema details (indexes, partitioning strategy)
- Invariant check placement and granularity
- Multi-hop swap detection algorithm (EVM log analysis, token transfer tracing)
- Offline mode detection mechanism (health check vs config flag vs automatic)
- Integration test scenario selection and coverage targets

### Deferred Ideas (OUT OF SCOPE)
- Digital signatures on report packages (key management complexity — future enhancement)
- Full offline cache layer with API response replay (v2)
- Real-time price updates via WebSocket
- Tax optimization suggestions
</user_constraints>

---

## Summary

Phase 11 is a hardening and gap-filling phase that builds directly on the infrastructure completed in Phases 1-10. Every work item has a clear attachment point in the existing codebase — no new architectural patterns are introduced. The work divides into five areas: (1) replace the narrow `classification_audit_log` with a universal `audit_log` table and wire it across all mutation points; (2) add MANIFEST.json generation to `PackageBuilder` and stale-report detection to the reports API; (3) inject runtime invariant guards into the four fragile subsystems (ACB, classifier, reconciler, exchange parsers) using the existing "flag + continue" pattern from `ACBPool.dispose()`; (4) extend `EVMDecoder` to handle multi-hop swaps beyond two tokens; (5) add an offline/cached mode gate to the indexer that skips network calls without crashing.

The project already has 436 tests. Phase 11 adds integration-level scenarios (not just unit mocks) for the invariant checks, and new unit tests for manifest validation and multi-hop detection.

**Primary recommendation:** Work area by area in migration-first order — Alembic migration 008 (unified audit table) must land before any code writes to it. MANIFEST generation and stale detection can be done in a single plan. Invariant checks across the four engines and multi-hop swap support can be done in parallel plans. Offline mode is the lowest-risk final plan.

---

## Standard Stack

### Core (all already in project)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg2 | existing | PostgreSQL driver | Project standard, all DB access uses pool |
| SQLAlchemy | existing | ORM + migration models | Migration models live in `db/models/_all_models.py` |
| Alembic | existing | Schema migrations | All 7 migrations follow same op.* pattern |
| FastAPI | existing | API layer | All routers live in `api/routers/` |
| pytest | existing | Test runner | 436 tests passing; `tests/conftest.py` fixtures established |
| hashlib | stdlib | SHA-256 checksums | Used in `api/routers/reports.py` already for path guard |
| json / pathlib | stdlib | MANIFEST.json writing | No new deps needed |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `decimal.Decimal` | stdlib | Monetary precision | All ACB/gains calculations; never float |
| `logging` | stdlib | Invariant violation logging | Every invariant violation logs before setting needs_review |
| `requests` | existing | HTTP for health checks | Used in `verify/reconcile.py`; reuse for offline detection |

### No New Dependencies Needed
Phase 11 introduces no new pip packages. Every capability (SHA-256, JSONB, Alembic migrations, pytest) is already available.

**Installation:** None required.

---

## Architecture Patterns

### Pattern 1: Unified Audit Table (migration 008)

**What:** Replace narrow `classification_audit_log` (classification-specific columns) with a generic `audit_log` table that accepts any entity type.

**Schema decision (Claude's discretion — recommended):**

```sql
CREATE TABLE audit_log (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id),
    entity_type     VARCHAR(50) NOT NULL,  -- 'transaction_classification', 'acb_snapshot', 'verification_result', 'report_package', 'duplicate_merge', 'manual_balance'
    entity_id       INTEGER,               -- nullable: some actions (report generation) have no single entity
    action          VARCHAR(50) NOT NULL,  -- 'initial_classify', 'reclassify', 'acb_correction', 'duplicate_merge', 'balance_override', 'report_generated', 'invariant_violation', 'verification_resolved'
    old_value       JSONB,                 -- NULL on initial creation
    new_value       JSONB NOT NULL,        -- serialized state after action
    actor_type      VARCHAR(20) NOT NULL,  -- 'system', 'user', 'specialist', 'ai'
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_al_entity ON audit_log (entity_type, entity_id);
CREATE INDEX ix_al_user_id ON audit_log (user_id);
CREATE INDEX ix_al_created_at ON audit_log (created_at);
CREATE INDEX ix_al_action ON audit_log (action);
```

**Migration strategy:**
1. In migration 008 `upgrade()`: create `audit_log` table
2. INSERT INTO audit_log SELECT (mapping old classification_audit_log columns to new schema)
3. DROP TABLE classification_audit_log
4. Update SQLAlchemy model `ClassificationAuditLog` → replace with `AuditLog` in `_all_models.py`

**Indexing (Claude's discretion):** No partitioning — the table will have tens of thousands of rows max for this user base; partitioning adds complexity without benefit. The composite index on `(entity_type, entity_id)` covers the primary query pattern (fetch history for a specific entity).

**Why use JSONB for old_value/new_value:** Consistent with `raw_data` on transactions and `diagnosis_detail` on verification_results. Allows arbitrary schema per entity type without ALTER TABLE.

### Pattern 2: Audit Writer Helper

**What:** A lightweight module `db/audit.py` that all mutation paths import for inserting audit rows. Avoids duplicating INSERT SQL across every handler.

```python
# Source: project pattern — same as sanitize_for_log() in config.py
def write_audit(conn, *, user_id, entity_type, entity_id=None, action,
                old_value=None, new_value, actor_type='system', notes=None):
    """Insert one audit_log row. Call within the caller's transaction boundary."""
    import json
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO audit_log
           (user_id, entity_type, entity_id, action, old_value, new_value, actor_type, notes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (user_id, entity_type, entity_id, action,
         json.dumps(old_value) if old_value else None,
         json.dumps(new_value), actor_type, notes)
    )
```

**Call sites to wire:**
- `engine/classifier/writer.py` — on initial classify and reclassify
- `engine/acb/engine_acb.py` — on ACB snapshot upsert and invariant violation
- `verify/duplicates.py` — on auto-merge
- `api/routers/transactions.py` — on manual classification edit (PUT endpoint)
- `api/routers/verification.py` — on verification resolution (POST /resolve)
- `reports/generate.py` — on PackageBuilder.build() completion (report_generated event)
- All four fragile-area invariant checkers — on invariant_violation events

### Pattern 3: MANIFEST.json in PackageBuilder

**What:** After all files are written, compute SHA-256 of each file and write MANIFEST.json to the output_dir.

**Manifest schema:**
```python
{
    "generated_at": "2026-03-14T10:00:00Z",          # ISO 8601 UTC
    "tax_year": 2024,
    "user_id": 1,
    "source_data_version": {
        "last_tx_timestamp": 1735689600,               # max block_timestamp in transactions
        "total_tx_count": 23679,                       # count(*) transactions for user
        "acb_snapshot_version": "2026-03-14T09:55:00Z", # max(updated_at) from acb_snapshots
        "needs_review_count": 3                        # count(*) where needs_review=True
    },
    "files": [
        {
            "filename": "capital_gains_2024.pdf",
            "sha256": "abc123...",
            "size_bytes": 45231
        }
    ]
}
```

**Placement:** Add `_write_manifest(output_dir, files, user_id, tax_year, conn)` as a final step in `PackageBuilder.build()` before the return statement.

**Stale detection in API:** In `api/routers/reports.py`, when listing or downloading a report package, read MANIFEST.json and compare `source_data_version` against current DB state. If fingerprint differs, include `{"stale": true, "reason": "..."}` in the response.

### Pattern 4: Runtime Invariant Checks — "Flag + Continue"

**What:** Inline assertions at critical computation points. On failure: log warning, call `write_audit()` with action='invariant_violation', set `needs_review=True` on the affected record, and return/continue rather than raising.

**Why "flag + continue":** Directly established in decisions: "Pipeline never halts on invariant violation." This matches `ACBPool.dispose()` which already does `needs_review=True; units = self.total_units` on oversell — it never raises.

**ACB invariants — placement: `engine/acb/pool.py` and `engine/acb/engine_acb.py`:**

```python
# After acquire(): pool balance must not be negative
def _check_acb_pool_consistency(pool, snapshot, conn=None, user_id=None):
    """Check: total_cost_cad >= 0, total_units >= 0."""
    violations = []
    if pool.total_cost_cad < 0:
        violations.append(f"negative total_cost_cad: {pool.total_cost_cad}")
    if pool.total_units < 0:
        violations.append(f"negative total_units: {pool.total_units}")
    if violations:
        logger.warning("ACB invariant violation %s: %s", pool.symbol, violations)
        # if conn provided, write audit row
        return False
    return True
```

**Classifier invariants — placement: `engine/classifier/writer.py` after upsert:**

```python
# Every tx must have exactly one parent classification
def _check_classifier_invariants(conn, user_id, transaction_id):
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM transaction_classifications "
        "WHERE user_id=%s AND transaction_id=%s AND leg_type='parent'",
        (user_id, transaction_id)
    )
    count = cur.fetchone()[0]
    if count != 1:
        logger.warning("Classifier invariant: tx %s has %d parent classifications", transaction_id, count)
        # write audit + set needs_review
```

**Reconciliation invariants — placement: `verify/reconcile.py` in `BalanceReconciler.reconcile_user()`:**
- Assert all wallets for user are covered before returning
- Assert diagnosis_category is set for every open result

**Exchange invariants — placement: `indexers/exchange_parsers/base.py` in `parse_row()`:**
- After `parse_row()` returns, validate: amount is non-zero, date is parseable, asset is non-empty
- On violation: log + mark that row as needs_review in the returned dict

### Pattern 5: Multi-Hop Swap Detection

**What:** Extend `EVMDecoder` to detect multi-hop routes from Uniswap V3 `exactInput` (already has selector `0xc04b8d59`) and similar aggregator calls. The `exactInput` ABI encodes the full path as a bytes parameter containing (tokenA, fee, tokenB, fee, tokenC...) — a sequence of 23-byte chunks.

**Algorithm (Claude's discretion — recommended):**

```python
def decode_multi_hop_path(self, input_hex: str) -> list[str]:
    """Decode Uniswap V3 exactInput path parameter into token list.

    Path encoding: [token_addr (20 bytes)][fee (3 bytes)][token_addr (20 bytes)]...
    Returns list of token addresses in hop order.
    """
    # Strip selector (4 bytes = 8 hex chars after '0x')
    # ABI decode to find path bytes parameter
    # Split into 20-byte token address chunks
    ...
```

For each intermediate token in the path, create an ACB acquire/dispose pair:
- Token A disposed → Token B acquired (at intermediate FMV)
- Token B disposed → Token C acquired (at intermediate FMV)
- etc.

**Practical constraint:** Intermediate FMV for non-listed tokens defaults to None with `price_estimated=True`. The classifier marks the parent as `needs_review=True` if any intermediate price is missing.

**Leg naming:** Multi-hop extends the existing leg_type system. A 3-hop swap (A→B→C) generates:
- parent: swap_leg_0 (overall context)
- sell_leg: A disposed
- intermediate_leg_1: B acquired then disposed (new leg_type value)
- buy_leg: C acquired

**Detection trigger:** `EVMDecoder.detect_swap()` already detects `exactInput` — extend it to return `hop_count` from the path byte length.

### Pattern 6: Offline / Cached Mode

**What:** A simple mode gate in the indexer that skips network calls when APIs are unavailable.

**Detection mechanism (Claude's discretion — recommended: health check on startup, config flag override):**

```python
# In config.py
OFFLINE_MODE = os.environ.get("OFFLINE_MODE", "auto").lower()
# "auto" = detect at startup via health check
# "true" = always offline
# "false" = always online (error on network failure)
```

**Health check target:** Attempt a single GET to `NEARBLOCKS_BASE_URL` with 3-second timeout on IndexerService startup. If it fails, set `_is_offline = True`.

**Gate placement:** In `IndexerService._run_job()`, before dispatching to any fetcher handler, check `_is_offline`. If offline, move job back to 'queued' status with `last_error='offline_mode'` rather than running it. Classification, ACB, verification, and report handlers proceed normally — they don't make network calls.

**API exposure:** Add `GET /api/status` endpoint (or extend the existing `/health`) to expose `{"offline_mode": bool, "reason": "..."}` so the UI can show the offline banner.

### Anti-Patterns to Avoid

- **Raising exceptions from invariant checks:** The "flag + continue" pattern is locked. `RuntimeError` on invariant failure would break the pipeline.
- **Writing audit rows outside the caller's transaction boundary:** `write_audit()` must be called within the same `conn` that's being committed. Don't open a separate connection.
- **Computing SHA-256 by reading files back after write:** Read file content once during PackageBuilder's file-writing loop, not by re-opening each file for the manifest step — `pathlib.Path(f).read_bytes()` is fine since files are local.
- **Storing MANIFEST.json inside the package then including it in its own hash list:** Compute hashes for all other files first, write MANIFEST.json, then do NOT include MANIFEST.json in its own `files` list (circular dependency).
- **Dropping `classification_audit_log` before migrating its data:** The migration must INSERT migrated rows before DROP TABLE in the same transaction.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SHA-256 file hashing | Custom hash loop | `hashlib.sha256(Path(f).read_bytes()).hexdigest()` | Already in stdlib; used in `api/routers/reports.py` for path-traversal guard |
| Audit INSERT boilerplate | Per-handler INSERT SQL | `db/audit.py` write_audit() helper | 8+ call sites need same INSERT; DRY |
| Offline network detection | Polling thread | Single health check on IndexerService startup + config flag | Simpler; no thread complexity; config flag gives manual override |
| Multi-hop path decoding for V3 | ABI decoder library | Byte-slicing on the known path encoding | Uniswap V3 path encoding is fixed-format; no full ABI library needed |
| Manifest staleness fingerprint | Separate staleness table | Read MANIFEST.json + query current counts inline | MANIFEST.json already has the snapshot metadata; DB query is cheap |

---

## Common Pitfalls

### Pitfall 1: Migration 008 Data Loss on classification_audit_log Drop

**What goes wrong:** If `upgrade()` drops `classification_audit_log` before INSERT INTO audit_log completes, existing audit history is lost.

**Why it happens:** Alembic runs all statements in sequence, but partial failures could leave the table dropped.

**How to avoid:** Use a single migration function: (1) CREATE TABLE audit_log, (2) INSERT INTO audit_log SELECT from classification_audit_log (with column mapping), (3) DROP TABLE classification_audit_log. Test `downgrade()` separately — it should DROP audit_log and re-CREATE classification_audit_log (though data migration on downgrade is not required for this use case).

**Warning signs:** `alembic upgrade head` completes but audit_log row count doesn't match old classification_audit_log count.

### Pitfall 2: Partial Unique Index Conflicts on audit_log

**What goes wrong:** Unlike `transaction_classifications`, audit_log is append-only (immutable). Adding a UNIQUE constraint would prevent re-logging the same action on retry.

**Why it happens:** Temptation to add `UNIQUE(entity_type, entity_id, action)` to prevent duplicates.

**How to avoid:** No unique constraint on audit_log. It is always INSERT-only. Idempotency is not needed — duplicate audit rows on retry are acceptable and expected.

### Pitfall 3: MANIFEST.json SHA-256 Computed Before File Write Completes

**What goes wrong:** If files are still being written when SHA-256 is computed, hashes are incorrect.

**Why it happens:** Asynchronous writes or partial flushes.

**How to avoid:** Compute SHA-256 after all `report_instance.generate()` calls complete. `PackageBuilder.build()` is synchronous — all generates complete before the manifest step. Use `Path(f).read_bytes()` on the finalized file.

### Pitfall 4: Invariant Check DB Round-Trips Slowing Pipeline

**What goes wrong:** Adding one SELECT per transaction to check classifier invariants makes the classify_transactions job 10x slower.

**Why it happens:** Per-transaction DB queries inside a loop.

**How to avoid:** Batch invariant checks where possible. For classifier invariants: check classification counts in a single GROUP BY query at the end of each `classify_transactions` job, not per-transaction. For ACB invariants: check pool state in-memory (no DB) — `ACBPool` state is already in memory.

### Pitfall 5: Audit Log Writes Breaking Existing Tests

**What goes wrong:** Adding `write_audit()` calls into `engine/classifier/writer.py` breaks existing classifier tests because the mock_conn doesn't expect the extra `cursor.execute()` call.

**Why it happens:** Tests mock `mock_cursor.execute` with side effects or assertion counts.

**How to avoid:** Make `write_audit()` fail silently when `conn` is None. All call sites that have a real conn should pass it; test-only callers that don't have a conn can pass `conn=None` and the audit write is skipped. Add a test for `write_audit()` itself separately.

### Pitfall 6: leg_type='intermediate_leg' Breaks Existing Partial Unique Index

**What goes wrong:** The migration 003 partial unique index `uq_tc_user_tx_leg` on `(user_id, transaction_id, leg_type)` prevents two intermediate legs for the same transaction.

**Why it happens:** Multi-hop swaps with A→B→C→D create multiple intermediate legs with the same base leg_type.

**How to avoid:** Include `leg_index` in the unique constraint. The existing `leg_index` column handles ordering — update the partial index in migration 008 to `(user_id, transaction_id, leg_type, leg_index)`. Or use distinct leg_type values: 'intermediate_leg_1', 'intermediate_leg_2', etc. The `leg_index` approach is cleaner.

---

## Code Examples

Verified patterns from codebase inspection:

### SHA-256 File Hashing for MANIFEST.json
```python
# Pattern: pathlib + hashlib — consistent with path-traversal guard in api/routers/reports.py
import hashlib
from pathlib import Path

def compute_sha256(filepath: str) -> str:
    return hashlib.sha256(Path(filepath).read_bytes()).hexdigest()

# In PackageBuilder._write_manifest():
manifest = {
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "tax_year": tax_year,
    "user_id": user_id,
    "source_data_version": _get_data_fingerprint(conn, user_id),
    "files": [
        {
            "filename": Path(f).name,
            "sha256": compute_sha256(f),
            "size_bytes": Path(f).stat().st_size,
        }
        for f in files
        if Path(f).exists()
    ],
}
manifest_path = os.path.join(output_dir, "MANIFEST.json")
Path(manifest_path).write_text(json.dumps(manifest, indent=2))
```

### Data Fingerprint Query
```python
# Pattern: single query for snapshot metadata — consistent with gate check in ReportEngine
def _get_data_fingerprint(conn, user_id: int) -> dict:
    cur = conn.cursor()
    cur.execute(
        """SELECT
               MAX(block_timestamp) AS last_tx_ts,
               COUNT(*)             AS total_tx_count
           FROM transactions WHERE user_id = %s""",
        (user_id,)
    )
    row = cur.fetchone()
    cur.execute(
        "SELECT MAX(updated_at) FROM acb_snapshots WHERE user_id = %s", (user_id,)
    )
    acb_row = cur.fetchone()
    cur.execute(
        "SELECT COUNT(*) FROM transaction_classifications WHERE user_id=%s AND needs_review=TRUE",
        (user_id,)
    )
    review_row = cur.fetchone()
    return {
        "last_tx_timestamp": row[0] if row else None,
        "total_tx_count": row[1] if row else 0,
        "acb_snapshot_version": acb_row[0].isoformat() if acb_row and acb_row[0] else None,
        "needs_review_count": review_row[0] if review_row else 0,
    }
```

### Alembic Migration 008 — Audit Log (structure)
```python
# Pattern follows 003_classification_schema.py exactly
# revision: "008", down_revision: "007"
def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_al_user_id"),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_al_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("ix_al_user_id", "audit_log", ["user_id"])
    op.create_index("ix_al_created_at", "audit_log", ["created_at"])
    op.create_index("ix_al_action", "audit_log", ["action"])

    # Migrate existing classification_audit_log rows
    op.execute("""
        INSERT INTO audit_log (user_id, entity_type, entity_id, action,
                               old_value, new_value, actor_type, notes, created_at)
        SELECT
            changed_by_user_id,
            'transaction_classification',
            classification_id,
            change_reason,
            CASE WHEN old_category IS NOT NULL
                 THEN jsonb_build_object('category', old_category, 'confidence', old_confidence)
                 ELSE NULL END,
            jsonb_build_object('category', new_category, 'confidence', new_confidence),
            changed_by_type,
            notes,
            created_at
        FROM classification_audit_log
    """)

    op.drop_table("classification_audit_log")
```

### ACB Invariant Check (in-memory, no DB round-trip)
```python
# Pattern: mirrors ACBPool.dispose() oversell clamp — flag + continue
def check_acb_pool_invariants(pool, conn=None, user_id=None, context=""):
    """Check ACBPool for consistency violations. Log + flag, never raise."""
    violations = []
    if pool.total_cost_cad < 0:
        violations.append(f"negative_total_cost_cad:{pool.total_cost_cad}")
    if pool.total_units < 0:
        violations.append(f"negative_total_units:{pool.total_units}")
    if violations and conn is not None:
        logger.warning("ACB invariant violation [%s] %s: %s", pool.symbol, context, violations)
        write_audit(conn, user_id=user_id, entity_type='acb_pool',
                    entity_id=None, action='invariant_violation',
                    new_value={"symbol": pool.symbol, "violations": violations,
                               "context": context},
                    actor_type='system')
    return len(violations) == 0
```

### Classifier Invariant Check (batch query, end of job)
```python
# Called once per classify_transactions job, not per-transaction
def check_classifier_invariants_batch(conn, user_id: int) -> list[dict]:
    """Find transactions with missing or duplicate parent classifications."""
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, COUNT(tc.id) as parent_count
        FROM transactions t
        LEFT JOIN transaction_classifications tc
            ON tc.transaction_id = t.id
            AND tc.user_id = %s
            AND tc.leg_type = 'parent'
        WHERE t.user_id = %s
        GROUP BY t.id
        HAVING COUNT(tc.id) != 1
        LIMIT 100
    """, (user_id, user_id))
    return [{"transaction_id": r[0], "parent_count": r[1]} for r in cur.fetchall()]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| `classification_audit_log` (narrow, classification-only) | Unified `audit_log` (all entity types, JSONB values) | Phase 11 | All mutations tracked in one place; API query simplified |
| No manifest on report package | MANIFEST.json with SHA-256 per file + data fingerprint | Phase 11 | Accountant can verify package integrity; stale detection possible |
| No runtime invariant checks | Inline invariant assertions at 4 engine boundaries | Phase 11 | Violations surfaced to review queue automatically |
| Only two-hop swap support in EVMDecoder | Multi-hop path decoding for V3 `exactInput` | Phase 11 | Accurate cost basis for DEX aggregator transactions |
| No offline mode — crashes on API timeout | Flag + continue; network-dependent jobs queued offline | Phase 11 | Safe operation during NearBlocks/Etherscan outages |

**Deprecated/outdated after Phase 11:**
- `classification_audit_log` table: dropped in migration 008; `ClassificationAuditLog` SQLAlchemy model replaced by `AuditLog`
- Any code that imports or references `ClassificationAuditLog` must be updated to use `AuditLog`

---

## Open Questions

1. **Intermediate token FMV for multi-hop swaps**
   - What we know: Intermediate tokens in a 3-hop route (e.g., USDC) may be fetchable from CoinGecko by address
   - What's unclear: CoinGecko's `coins/{id}/market_chart` requires a CoinGecko coin ID, not a contract address — lookup from address requires an extra API call
   - Recommendation: For Phase 11, set intermediate FMV to None with `price_estimated=True` and `needs_review=True`. Document this in invariant violation notes. Full price resolution for intermediate hops is a Phase 12 enhancement.

2. **Offline mode detection granularity**
   - What we know: The config flag approach is flexible; the health check approach is automatic
   - What's unclear: Should offline mode be per-API (NearBlocks offline but Etherscan online) or global?
   - Recommendation: Global offline mode first (simpler). Per-API granularity is a future enhancement.

3. **audit_log volume concerns**
   - What we know: Report generation events, invariant violations, and manual edits will all write rows
   - What's unclear: At scale, could this table grow large? (For this single-user scenario: no — thousands of rows, not millions)
   - Recommendation: No partitioning for Phase 11. Add a note in the audit_log model that partitioning by month is the future path if needed.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (436 tests currently passing) |
| Config file | `pyproject.toml` (has `[project]` table; pytest settings via `pytest.ini` or inline) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Behavior | Test Type | Automated Command | File Exists? |
|----------|-----------|-------------------|-------------|
| audit_log migration 008 creates table and migrates data | integration | `pytest tests/test_audit_log.py -x` | ❌ Wave 0 |
| write_audit() inserts row with correct fields | unit | `pytest tests/test_audit_log.py::test_write_audit -x` | ❌ Wave 0 |
| PackageBuilder generates MANIFEST.json alongside reports | unit | `pytest tests/test_reports.py::test_manifest_generation -x` | ❌ new test in existing file |
| Stale detection: fingerprint mismatch returns stale=True | unit | `pytest tests/test_api_reports.py::test_stale_detection -x` | ❌ new test in existing file |
| ACB invariant check flags negative pool balance | unit | `pytest tests/test_acb.py::test_acb_invariant_negative_balance -x` | ❌ new test in existing file |
| Classifier invariant: tx with 0 parent classifications detected | unit | `pytest tests/test_classifier.py::test_classifier_invariant_missing_parent -x` | ❌ new test in existing file |
| Reconciler invariant: all wallets covered | integration | `pytest tests/test_invariants.py::test_reconciler_coverage -x` | ❌ Wave 0 |
| Exchange parser invariant: zero-amount row flagged | unit | `pytest tests/test_exchange_parsers.py::test_parser_invariant_zero_amount -x` | ❌ new test in existing file |
| EVMDecoder: 3-hop swap decoded correctly | unit | `pytest tests/test_evm_decoder.py::test_multi_hop_3_token -x` | ❌ new test in existing file |
| Offline mode: indexer queues job rather than crashing | unit | `pytest tests/test_offline_mode.py -x` | ❌ Wave 0 |
| Audit API: GET /audit/history returns rows for entity | unit | `pytest tests/test_api_audit.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_audit_log.py` — covers audit table creation and write_audit()
- [ ] `tests/test_invariants.py` — covers reconciler and integrated invariant scenarios
- [ ] `tests/test_offline_mode.py` — covers offline gate in IndexerService
- [ ] `tests/test_api_audit.py` — covers GET /audit/history endpoint
- [ ] `db/audit.py` — the write_audit() helper module (implementation, not just test)

---

## Sources

### Primary (HIGH confidence)
- **Codebase direct inspection** — `db/migrations/versions/003_classification_schema.py`, `db/models/_all_models.py`, `engine/acb/pool.py`, `engine/evm_decoder.py`, `reports/generate.py`, `indexers/nearblocks_client.py`, `verify/reconcile.py`, `engine/classifier/rules.py`, `indexers/exchange_parsers/base.py`, `config.py`, `tests/conftest.py`
- **Git history and STATE.md** — all architectural decisions, migration sequence, test counts

### Secondary (MEDIUM confidence)
- **Uniswap V3 path encoding** — V3 `exactInput` path ABI encoding is well-documented; 20-byte address + 3-byte fee chunks is the canonical format; validated against the selector `0xc04b8d59` already in EVMDecoder

### Tertiary (LOW confidence — not critical for this phase)
- General PostgreSQL append-only audit table patterns from community practice — consistent with the project's established JSONB patterns

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all libraries verified in existing codebase
- Architecture: HIGH — all patterns derived from existing code (ACBPool.dispose, migration 003, PackageBuilder, conftest.py)
- Pitfalls: HIGH — derived from specific existing code patterns and constraints (partial unique indexes, test mock patterns)
- Multi-hop decode: MEDIUM — byte-slicing approach correct for V3 exactInput, but intermediate FMV resolution is an open question

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (stable domain; project codebase is the primary source)
