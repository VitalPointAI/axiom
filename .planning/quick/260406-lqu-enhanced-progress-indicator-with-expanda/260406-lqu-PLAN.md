---
phase: quick-260406-lqu
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - web/components/sync-status.tsx
  - web/components/progress-detail-panel.tsx
autonomous: true
requirements: [QUICK-enhanced-progress-indicator]
must_haves:
  truths:
    - "Clicking the compact progress badge in the header opens an expandable dropdown panel"
    - "The panel shows which pipeline stage is active with a stage stepper (Indexing, Classifying, Cost Basis, Verifying)"
    - "The panel shows an overall progress bar across all stages (0-100%)"
    - "The panel shows a progress bar for the current active stage"
    - "The panel lists individual jobs with their type, status, and progress_fetched/progress_total"
    - "The panel updates in real-time via the existing 3s polling"
    - "Clicking outside the panel or clicking the badge again closes it"
    - "The panel does NOT appear when status is done/up-to-date"
    - "Wallet-specific and compact modes are unchanged"
  artifacts:
    - path: "web/components/progress-detail-panel.tsx"
      provides: "Expandable progress detail dropdown component"
    - path: "web/components/sync-status.tsx"
      provides: "Updated SyncStatus with clickable badge and full job type data"
  key_links:
    - from: "web/components/sync-status.tsx"
      to: "web/components/progress-detail-panel.tsx"
      via: "import and render in global mode"
    - from: "web/components/sync-status.tsx"
      to: "/api/jobs/active"
      via: "existing fetch — now passes full ActiveJobsResponse to panel"
---

<objective>
Make the global header progress badge clickable, opening an expandable dropdown panel that shows pipeline stage breakdown, overall and per-stage progress bars, and individual job details with real-time progress.

Purpose: Users currently see only a single-line summary ("Cost Basis 65% -- 13 jobs active -- ~27 min remaining"). They have no visibility into which specific jobs are running, what stage each is in, or per-job progress. This expandable detail gives power users transparency into the processing pipeline.

Output: Updated SyncStatus component with clickable badge, new ProgressDetailPanel component.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@web/components/sync-status.tsx
@web/app/dashboard/layout.tsx
@api/schemas/jobs.py
@api/routers/jobs.py

<interfaces>
<!-- Backend API contract (already deployed, no changes needed) -->

From api/schemas/jobs.py:
```python
class JobStatusResponse(BaseModel):
    id: int
    job_type: str           # full_sync, classify_transactions, calculate_acb, verify_balances, etc.
    status: str             # queued | running | completed | failed | retrying
    progress_fetched: Optional[int] = None
    progress_total: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class ActiveJobsResponse(BaseModel):
    jobs: List[JobStatusResponse]
    pipeline_stage: str     # Indexing | Classifying | Cost Basis | Verifying | Done | Idle
    pipeline_pct: int       # 0-100
    estimated_minutes: Optional[int] = None
```

From api/routers/jobs.py - stage map for reference:
```python
_STAGE_MAP = {
    "full_sync": ("Indexing", 0, 45),
    "incremental_sync": ("Indexing", 0, 45),
    "staking_sync": ("Indexing", 0, 45),
    "lockup_sync": ("Indexing", 0, 45),
    "evm_full_sync": ("Indexing", 0, 45),
    "evm_incremental": ("Indexing", 0, 45),
    "file_import": ("Importing", 0, 45),
    "dedup_scan": ("Classifying", 45, 65),
    "classify_transactions": ("Classifying", 45, 65),
    "calculate_acb": ("Cost Basis", 65, 85),
    "verify_balances": ("Verifying", 85, 100),
    "generate_reports": ("Verifying", 85, 100),
}
```

From web/app/dashboard/layout.tsx (line 122):
```tsx
<SyncStatus />  <!-- Global mode: no walletId prop -->
```

Current SyncStatus ActiveJobsResponse type (line 45-50, NEEDS UPDATING):
```tsx
interface ActiveJobsResponse {
  jobs: Array<{ status: string; pipeline_stage: string; pipeline_pct: number }>;
  pipeline_stage: string;
  pipeline_pct: number;
  estimated_minutes: number | null;
}
```
The jobs array type is incomplete -- it only has status/pipeline_stage/pipeline_pct but the API actually returns full JobStatusResponse fields (id, job_type, progress_fetched, progress_total, error_message, started_at, completed_at). The type must be updated to match the real API response.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create ProgressDetailPanel component</name>
  <files>web/components/progress-detail-panel.tsx</files>
  <action>
Create a new component `ProgressDetailPanel` that renders as an absolutely-positioned dropdown panel anchored below the header badge.

**Props interface:**
```tsx
interface ProgressDetailPanelProps {
  jobs: JobDetail[];
  pipelineStage: string;
  pipelinePct: number;
  estimatedMinutes: number | null;
  onClose: () => void;
}

interface JobDetail {
  id: number;
  job_type: string;
  status: string;
  progress_fetched: number | null;
  progress_total: number | null;
  error_message: string | null;
  started_at: string | null;
}
```

**Panel layout (top to bottom):**

1. **Header row**: "Processing Details" title on left, X close button on right (lucide-react `X` icon). Use `text-sm font-semibold text-gray-200`.

2. **Pipeline stage stepper**: Horizontal row of 4 stages (Indexing, Classifying, Cost Basis, Verifying). Each stage shows:
   - A small circle indicator: green filled if complete, blue pulsing if active, gray if pending
   - Stage label below in `text-xs`
   - Connected by a thin line between circles (same pattern as existing per-wallet view but horizontal and compact)
   - Determine active/complete by mapping `pipelineStage` prop to stage index. Stages before active = complete, active = active, after = pending.

3. **Overall progress section**:
   - Label: "Overall Progress" with `{pipelinePct}%` on the right, `text-xs text-gray-400`
   - Full-width progress bar: `h-2 bg-gray-700 rounded-full` with `bg-blue-500` fill
   - Below the bar: estimated time remaining in `text-xs text-gray-500` (format: "~X min remaining" or "~Xh remaining")

4. **Current stage progress section**:
   - Label: "{pipelineStage}" with stage-specific percentage on right
   - Calculate stage-specific percentage: use the same stage ranges from the backend (Indexing 0-45, Classifying 45-65, Cost Basis 65-85, Verifying 85-100). The within-stage pct = `((pipelinePct - stageMin) / (stageMax - stageMin)) * 100`, clamped 0-100.
   - Narrower progress bar in stage-specific color: Indexing=blue-500, Classifying=purple-500, Cost Basis=amber-500, Verifying=green-500

5. **Active jobs list**: Scrollable area (`max-h-48 overflow-y-auto`) listing each job:
   - Each job row: `flex items-center justify-between py-1.5 border-b border-gray-800 last:border-0`
   - Left side: job type label (human-readable, e.g. "full_sync" -> "Full Sync", "calculate_acb" -> "Cost Basis Calc", "classify_transactions" -> "Classify", "verify_balances" -> "Verify Balances", "evm_full_sync" -> "EVM Sync", etc.) with a status indicator dot (green=running, yellow=queued, red=retrying, gray=failed)
   - Right side: progress fraction `"{fetched}/{total}"` if both are non-null, otherwise status text ("Queued", "Running...", "Retrying...")
   - If job has progress_fetched and progress_total, show a tiny inline progress bar (`h-1 w-16`) below the job label
   - If job has error_message (failed status), show truncated error in `text-xs text-red-400` below the row

**Styling:**
- Panel: `absolute right-0 top-full mt-2 w-80 sm:w-96 bg-gray-850 border border-gray-700 rounded-lg shadow-xl z-50 p-4 space-y-3`
- Since `bg-gray-850` is not standard Tailwind, use `bg-[#1a1f2e]` or `bg-gray-800` with a slightly lighter feel. Check the existing app's dark theme and match -- use `bg-gray-800 border-gray-700`.
- Add a small upward-pointing triangle/caret at the top-right of the panel using a CSS pseudo-element or a small div with border trick, for visual anchoring. Keep it simple -- if complex, skip it.

**Click-outside handling:** Use a `useEffect` with a `mousedown` event listener on `document`. If click target is outside the panel ref, call `onClose()`. Use `useRef<HTMLDivElement>` for the panel container.

**Export:** Named export `ProgressDetailPanel`.
  </action>
  <verify>
    <automated>cd /home/vitalpointai/projects/Axiom && npx tsc --noEmit web/components/progress-detail-panel.tsx 2>&1 | head -20; echo "---"; test -f web/components/progress-detail-panel.tsx && echo "FILE EXISTS" || echo "FILE MISSING"</automated>
  </verify>
  <done>ProgressDetailPanel component exists, exports correctly, TypeScript compiles without errors. Shows pipeline stepper, overall progress bar, stage progress bar, and per-job list with progress fractions.</done>
</task>

<task type="auto">
  <name>Task 2: Wire clickable badge and dropdown into SyncStatus global mode</name>
  <files>web/components/sync-status.tsx</files>
  <action>
Modify the existing SyncStatus component to add expandable detail panel in global mode.

**Step 1: Update the ActiveJobsResponse interface (line 45-50)**

Replace the incomplete jobs array type with the full shape matching the real API:
```tsx
interface JobDetail {
  id: number;
  job_type: string;
  status: string;
  progress_fetched: number | null;
  progress_total: number | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

interface ActiveJobsResponse {
  jobs: JobDetail[];
  pipeline_stage: string;
  pipeline_pct: number;
  estimated_minutes: number | null;
}
```

**Step 2: Store full ActiveJobsResponse in state for global mode**

Add new state to the component:
```tsx
const [activeJobsData, setActiveJobsData] = useState<ActiveJobsResponse | null>(null);
const [detailOpen, setDetailOpen] = useState(false);
```

In the `fetchStatus` function, inside the `else` block (global mode, line 67), after setting status, also store the raw response:
```tsx
setActiveJobsData(data);
```
When jobs array is empty (done state), set `setActiveJobsData(null)`.

**Step 3: Make the global badge clickable**

In the global mode active state render (lines 174-180), wrap the existing badge content in a `<button>` instead of `<div>`. The button should:
- Use `cursor-pointer` class
- `onClick={() => setDetailOpen(!detailOpen)}`
- Add `hover:bg-gray-800/50 rounded-md px-2 py-1 -mx-2 -my-1 transition-colors` for hover feedback
- Keep all existing content inside (RefreshCw icon, stage text, detail text)
- Add a `ChevronDown` icon from lucide-react at the end, with `w-3 h-3 ml-1 transition-transform` and `rotate-180` when detailOpen is true

Wrap the button in a `<div className="relative">` so the dropdown can be absolutely positioned.

**Step 4: Render the ProgressDetailPanel**

Import `ProgressDetailPanel` from `./progress-detail-panel`.

Immediately after the button, conditionally render:
```tsx
{detailOpen && activeJobsData && (
  <ProgressDetailPanel
    jobs={activeJobsData.jobs}
    pipelineStage={activeJobsData.pipeline_stage}
    pipelinePct={activeJobsData.pipeline_pct}
    estimatedMinutes={activeJobsData.estimated_minutes}
    onClose={() => setDetailOpen(false)}
  />
)}
```

**Step 5: Close panel on done transition**

In the existing done-transition effect (line 123-137), when status transitions to done, also `setDetailOpen(false)`.

**Step 6: Import ChevronDown**

Add `ChevronDown` to the lucide-react import on line 4.

**IMPORTANT: Do NOT modify the per-wallet or compact render paths.** Only the global mode (walletId === undefined) active state gets the clickable behavior. The done state ("Up to date") remains non-clickable.
  </action>
  <verify>
    <automated>cd /home/vitalpointai/projects/Axiom && npx tsc --noEmit web/components/sync-status.tsx 2>&1 | head -20; echo "---"; grep -c "ProgressDetailPanel" web/components/sync-status.tsx; grep -c "detailOpen" web/components/sync-status.tsx; grep -c "ChevronDown" web/components/sync-status.tsx</automated>
  </verify>
  <done>SyncStatus global mode badge is clickable, opens ProgressDetailPanel dropdown. ActiveJobsResponse type matches real API shape with full job details. Panel closes on click-outside or badge re-click. Per-wallet and compact modes are unchanged. TypeScript compiles cleanly.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| API -> Frontend | Job data from /api/jobs/active is already auth-gated and sanitized by the backend |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | I (Information Disclosure) | progress-detail-panel.tsx | accept | Job data only shown to authenticated user; API already enforces user_id scoping. Error messages may contain internal details but are truncated in UI display. |
| T-quick-02 | D (Denial of Service) | sync-status.tsx | accept | Polling interval unchanged at 3s; dropdown does not trigger additional API calls. No new attack surface. |
</threat_model>

<verification>
1. TypeScript compiles: `cd web && npx tsc --noEmit` passes with no errors in modified files
2. Visual: When jobs are active, clicking the header progress badge opens a dropdown showing stage stepper, overall progress bar, current stage progress bar, and individual job rows with progress
3. Visual: Clicking outside the panel or clicking the badge again closes the dropdown
4. Visual: When no jobs are active ("Up to date"), the badge is NOT clickable
5. Visual: Per-wallet and compact SyncStatus renders are visually identical to before
6. Real-time: Panel content updates every 3s matching the existing polling interval
</verification>

<success_criteria>
- Header progress badge is clickable and opens a detail dropdown
- Dropdown shows 4-stage pipeline stepper with active/complete/pending states
- Dropdown shows overall progress bar with percentage and estimated time
- Dropdown shows current-stage progress bar with stage-specific color
- Dropdown lists individual jobs with type, status, and progress fraction
- Dropdown closes on outside click or badge re-click
- No changes to per-wallet or compact mode rendering
- TypeScript compiles cleanly
</success_criteria>

<output>
After completion, create `.planning/quick/260406-lqu-enhanced-progress-indicator-with-expanda/260406-lqu-SUMMARY.md`
</output>
