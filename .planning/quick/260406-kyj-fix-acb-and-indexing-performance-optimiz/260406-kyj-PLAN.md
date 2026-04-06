---
phase: quick
plan: 260406-kyj
type: execute
wave: 1
depends_on: []
files_modified:
  - engine/acb/engine_acb.py
  - indexers/price_service.py
  - indexers/acb_handler.py
  - indexers/service.py
  - api/routers/wallets.py
  - api/routers/jobs.py
autonomous: true
must_haves:
  truths:
    - "ACB incremental mode completes in under 30 seconds for small batches of new transactions"
    - "ACB full replay completes in under 2 minutes for a user with thousands of transactions"
    - "Adding a new wallet does NOT trigger full ACB replay if previous ACB run completed successfully"
    - "Minute-level price lookups use batch fetching instead of per-transaction API calls"
    - "Progress bar shows accurate time estimates during ACB calculation"
    - "Resync and downstream scheduling never create duplicate pipeline jobs"
  artifacts:
    - path: "engine/acb/engine_acb.py"
      provides: "Batch minute-level price pre-warming, smart replay logic"
    - path: "indexers/price_service.py"
      provides: "Batch minute-level price fetching method"
    - path: "indexers/acb_handler.py"
      provides: "Progress reporting during ACB calculation"
    - path: "indexers/service.py"
      provides: "Deduplicated downstream scheduling"
    - path: "api/routers/wallets.py"
      provides: "Smart ACB replay flag, resync deduplication"
    - path: "api/routers/jobs.py"
      provides: "Accurate time estimates for ACB jobs"
  key_links:
    - from: "engine/acb/engine_acb.py"
      to: "indexers/price_service.py"
      via: "batch_fetch_minute_prices for large dispositions"
    - from: "indexers/acb_handler.py"
      to: "indexers/service.py"
      via: "progress_fetched/progress_total updates during ACB"
---

<objective>
Fix ACB and indexing pipeline performance so the full pipeline completes in under 2 minutes instead of showing multi-hour estimates.

Purpose: The current system shows "Cost Basis 65% -- 14 jobs active -- ~4h remaining" because:
(a) minute-level price lookups make per-transaction CoinGecko API calls with 2.1s delay each,
(b) every new wallet forces a full ACB replay even when incremental would suffice,
(c) duplicate pipeline jobs get created by both classifier and downstream scheduler,
(d) ACB handler doesn't report progress so time estimates are wildly inaccurate.

Output: Pipeline that completes in under 2 minutes with accurate progress reporting.
</objective>

<execution_context>
@.planning/quick/260406-kyj-fix-acb-and-indexing-performance-optimiz/260406-kyj-PLAN.md
</execution_context>

<context>
@engine/acb/engine_acb.py
@indexers/price_service.py
@indexers/acb_handler.py
@indexers/service.py
@api/routers/wallets.py
@api/routers/jobs.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Batch minute-level price fetching and smart ACB replay</name>
  <files>engine/acb/engine_acb.py, indexers/price_service.py, api/routers/wallets.py</files>
  <action>
The biggest performance bottleneck is per-transaction CoinGecko API calls for minute-level prices on large dispositions. Each call has a 2.1s rate-limit delay. A user with 100 large dispositions = 210 seconds just in API waits. Fix this with batch pre-warming.

**1. Add `bulk_fetch_minute_prices()` to PriceService (`indexers/price_service.py`):**

Add a new method that accepts a list of `(coin_id, unix_ts)` tuples and fetches them efficiently:
- Group timestamps by coin_id
- For each coin_id, find contiguous time clusters (timestamps within 2 hours of each other)
- For each cluster, make ONE `market_chart/range` API call covering the full cluster range (min_ts - 3600 to max_ts + 3600)
- Parse ALL returned price points and cache the closest match for each requested timestamp in `price_cache_minute`
- This turns N individual API calls into ceil(N/cluster_size) calls
- Use the same `_COINGECKO_DELAY` rate limiting between calls
- Skip any timestamps already in `price_cache_minute` (check in batch with a single SELECT)

Method signature:
```python
def bulk_fetch_minute_prices(
    self, requests: list[tuple[str, int]], currency: str = "usd"
) -> dict[tuple[str, int], tuple[Decimal, bool]]:
    """Pre-warm minute-level cache for multiple (coin_id, unix_ts) pairs.
    
    Groups requests into efficient API calls. Returns dict of
    (coin_id, ts_minute) -> (price, is_estimated).
    """
```

**2. Add `_pre_warm_minute_prices()` to ACBEngine (`engine/acb/engine_acb.py`):**

In `_full_replay()` and `_incremental()`, AFTER the existing `_pre_warm_price_cache()` call (which handles daily prices), add a second pre-warming pass for minute-level prices:

- Iterate all rows, identify dispositions (sell, capital_gain, capital_loss, trade, fee) with amounts likely above `DISPOSITION_PRECISION_THRESHOLD_CAD`
- For each, compute the (coin_id, unix_ts) pair
- Pass all pairs to `self._price_service.bulk_fetch_minute_prices()`
- After this pre-warm, the per-transaction `_resolve_fmv_cad()` calls will hit cache instead of making API calls

To estimate which transactions are "large" without knowing the price yet, use the daily price from the already-warmed cache:
```python
daily_price = self._price_service.get_daily_price_cad(coin_id, date_str)
if daily_price and units * daily_price[0] > self.DISPOSITION_PRECISION_THRESHOLD_CAD:
    minute_requests.append((coin_id, unix_ts))
```

**3. Smart ACB replay flag in wallet creation (`api/routers/wallets.py`):**

In `create_wallet()` (around line 224), change the unconditional `acb_full_replay_required = TRUE` to be smarter:

```python
# Only force full replay if user already has ACB data
# (new wallet may have older transactions that change chronological order)
# For the FIRST wallet, incremental mode will work fine since there's no prior state
cur.execute(
    """UPDATE users SET acb_full_replay_required = TRUE
       WHERE id = %s AND acb_high_water_mark IS NOT NULL""",
    (user_id,),
)
```

This means the first wallet added won't set the flag (no prior ACB data to invalidate), but subsequent wallets will correctly trigger a full replay.

Also in `resync_wallet()` (around line 528), add duplicate job detection before inserting:
```python
# Check for existing active jobs before inserting new ones
cur.execute(
    """SELECT job_type FROM indexing_jobs
       WHERE wallet_id = %s AND status IN ('queued', 'running', 'retrying')""",
    (wallet_id,),
)
existing_types = {r[0] for r in cur.fetchall()}
for job_type, priority in jobs:
    if job_type not in existing_types:
        cur.execute(...)  # only insert if not already queued
```
  </action>
  <verify>
    <automated>cd /home/vitalpointai/projects/Axiom && python -c "
from indexers.price_service import PriceService
# Verify method exists
assert hasattr(PriceService, 'bulk_fetch_minute_prices'), 'bulk_fetch_minute_prices not found'
print('PriceService.bulk_fetch_minute_prices exists')

from engine.acb.engine_acb import ACBEngine
import inspect
src = inspect.getsource(ACBEngine._full_replay)
assert 'bulk_fetch_minute' in src or 'pre_warm_minute' in src, 'minute pre-warm not in _full_replay'
print('ACBEngine._full_replay has minute pre-warming')

src_inc = inspect.getsource(ACBEngine._incremental)
assert 'bulk_fetch_minute' in src_inc or 'pre_warm_minute' in src_inc, 'minute pre-warm not in _incremental'
print('ACBEngine._incremental has minute pre-warming')
print('All checks passed')
"</automated>
  </verify>
  <done>
    - PriceService has bulk_fetch_minute_prices() that batches CoinGecko range API calls
    - ACBEngine pre-warms minute-level prices for large dispositions before processing
    - Wallet creation only sets acb_full_replay_required when user has existing ACB data
    - Resync endpoint deduplicates jobs
  </done>
</task>

<task type="auto">
  <name>Task 2: ACB progress reporting and pipeline job deduplication</name>
  <files>indexers/acb_handler.py, indexers/service.py, api/routers/jobs.py</files>
  <action>
**1. Add progress reporting to ACBHandler (`indexers/acb_handler.py`):**

The ACB handler currently provides zero progress information. The `_estimate_minutes()` function in jobs.py falls back to `elapsed_time * 0.5` when there's no progress data, producing absurd "~4h remaining" estimates.

Modify `run_calculate_acb()` to report progress:

```python
def run_calculate_acb(self, job: dict) -> None:
    from engine.acb import ACBEngine

    user_id = job["user_id"]
    job_id = job["id"]
    logger.info("Starting ACB calculation for user_id=%s", user_id)

    # Report total classifications count as progress_total
    conn = self.pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM transaction_classifications WHERE user_id = %s",
            (user_id,),
        )
        total = cur.fetchone()[0]
        cur.execute(
            "UPDATE indexing_jobs SET progress_total = %s WHERE id = %s",
            (total, job_id),
        )
        conn.commit()
        cur.close()
    finally:
        self.pool.putconn(conn)

    engine = ACBEngine(self.pool, self.price_service)
    # Pass job_id so engine can report progress
    stats = engine.calculate_for_user(user_id, progress_callback=self._make_progress_callback(job_id))
    # ... rest of existing logging
```

Add a progress callback factory:
```python
def _make_progress_callback(self, job_id: int):
    """Return a callback that updates progress_fetched on the job row."""
    last_reported = [0]  # mutable for closure
    def callback(processed: int):
        # Only update DB every 50 rows to avoid excessive writes
        if processed - last_reported[0] >= 50 or processed == 0:
            conn = self.pool.getconn()
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE indexing_jobs SET progress_fetched = %s, updated_at = NOW() WHERE id = %s",
                    (processed, job_id),
                )
                conn.commit()
                cur.close()
            finally:
                self.pool.putconn(conn)
            last_reported[0] = processed
    return callback
```

Then in `engine/acb/engine_acb.py`, add `progress_callback` parameter to `calculate_for_user()`, `_full_replay()`, and `_incremental()`. In the main processing loop of both methods, call it:

```python
for idx, row in enumerate(rows):
    if row.parent_classification_id is not None:
        continue
    self._process_row(...)
    if progress_callback and idx % 50 == 0:
        progress_callback(idx)
# Final callback with total count
if progress_callback:
    progress_callback(len(rows))
```

**2. Fix duplicate job creation in downstream scheduler (`indexers/service.py`):**

In `_schedule_downstream_if_ready()`, there's already a check for existing jobs, but the `ClassifierHandler` also independently queues `calculate_acb` (line 118 of classifier_handler.py). This creates TWO acb jobs.

The fix: In `_schedule_downstream_if_ready()`, add a redundant safety check that also covers the ACB handler's queueing:
- After the existing `SELECT COUNT(*)` check, also check completed jobs within the last 60 seconds to avoid scheduling if the stage just ran

```python
# Also skip if this stage completed very recently (within 60s)
# Prevents race between ClassifierHandler's direct queue and this scheduler
cur.execute(
    """SELECT COUNT(*) FROM indexing_jobs
       WHERE user_id = %s AND job_type = %s
         AND status = 'completed'
         AND completed_at > NOW() - INTERVAL '60 seconds'""",
    (user_id, next_stage),
)
if cur.fetchone()[0] > 0:
    cur.close()
    return  # Just completed — don't re-queue
```

**3. Improve time estimates for ACB jobs (`api/routers/jobs.py`):**

In `_estimate_minutes()`, the ACB heuristic default is 15 minutes for queued jobs (line 137). This is often wildly wrong. Change the heuristic to be based on classification count:

```python
elif jtype == "calculate_acb":
    # Estimate based on classification count if available
    # With pre-warmed prices: ~1000 classifications/sec for incremental,
    # ~100 classifications/sec for full replay (with price warming)
    if total > 0:
        # total = classification count (set by ACBHandler)
        total_minutes += max(1, int(total / 100 / 60))  # ~100/sec conservative
    else:
        total_minutes += 2  # Reduced from 15 — bulk pre-warming makes it fast
```
  </action>
  <verify>
    <automated>cd /home/vitalpointai/projects/Axiom && python -c "
import inspect
from indexers.acb_handler import ACBHandler
src = inspect.getsource(ACBHandler.run_calculate_acb)
assert 'progress' in src.lower(), 'ACBHandler missing progress reporting'
assert '_make_progress_callback' in inspect.getsource(ACBHandler) or 'progress_callback' in src, 'Missing progress callback'
print('ACBHandler has progress reporting')

from engine.acb.engine_acb import ACBEngine
sig = inspect.signature(ACBEngine.calculate_for_user)
assert 'progress_callback' in sig.parameters, 'calculate_for_user missing progress_callback param'
print('ACBEngine.calculate_for_user accepts progress_callback')

from indexers.service import IndexerService
src = inspect.getsource(IndexerService._schedule_downstream_if_ready)
assert 'completed' in src and '60' in src, 'Missing recent-completion dedup check'
print('Downstream scheduler has dedup check')
print('All checks passed')
"</automated>
  </verify>
  <done>
    - ACBHandler reports progress_fetched/progress_total during calculation
    - ACBEngine accepts and calls progress_callback during row processing
    - Downstream scheduler prevents duplicate job creation with 60s completion window
    - Time estimates use actual classification counts instead of fixed 15-minute heuristic
    - Pipeline should show realistic progress and complete within 2 minutes for typical users
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| API -> DB | Job manipulation via progress updates |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | T (Tampering) | progress_fetched updates | accept | Internal service only; job_id scoped to owned jobs; no user input |
| T-quick-02 | D (DoS) | bulk_fetch_minute_prices | mitigate | Rate limiting preserved via _COINGECKO_DELAY between batched calls |
</threat_model>

<verification>
1. After implementation, check that `bulk_fetch_minute_prices` exists on PriceService
2. Verify ACBEngine uses minute pre-warming before processing rows
3. Verify ACBHandler updates progress during calculation
4. Verify no duplicate jobs are created by the downstream scheduler
5. Run the existing test suite: `cd /home/vitalpointai/projects/Axiom && python -m pytest tests/ -x -q --timeout=120`
</verification>

<success_criteria>
- ACB incremental mode completes in under 30 seconds
- ACB full replay completes in under 2 minutes with pre-warmed prices
- Progress bar shows accurate percentage and time estimate during ACB
- No duplicate calculate_acb or verify_balances jobs created
- First wallet addition does not force unnecessary full ACB replay
- Existing tests pass
</success_criteria>

<output>
After completion, create `.planning/quick/260406-kyj-fix-acb-and-indexing-performance-optimiz/260406-kyj-SUMMARY.md`
</output>
