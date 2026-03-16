---
phase: quick-2
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - web/app/onboarding/steps/import.tsx
autonomous: true
requirements: []
must_haves:
  truths:
    - "Onboarding step 3 file upload sends POST to /api/exchanges/import (correct FastAPI endpoint)"
    - "Upload uses API_URL prefix so it works in both dev and production"
    - "FormData upload does not set Content-Type: application/json (lets browser set multipart boundary)"
  artifacts:
    - path: "web/app/onboarding/steps/import.tsx"
      provides: "Fixed upload URL and API_URL prefix"
  key_links:
    - from: "web/app/onboarding/steps/import.tsx"
      to: "api/routers/reports.py (exchanges_router)"
      via: "fetch POST /api/exchanges/import"
      pattern: "fetch.*api/exchanges/import"
---

<objective>
Fix the 404 error on exchange file upload in the onboarding wizard.

Purpose: The onboarding step 3 "Import Exchanges" POSTs to `/api/upload-file` which does not exist. The actual FastAPI endpoint is `POST /api/exchanges/import` (defined in `api/routers/reports.py` via `exchanges_router`). Additionally, the fetch call uses a relative URL without the `API_URL` prefix, which breaks in environments where the API is on a different host.

Output: Working file upload in onboarding wizard step 3.
</objective>

<execution_context>
@/home/vitalpointai/.claude/get-shit-done/workflows/execute-plan.md
@/home/vitalpointai/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@web/app/onboarding/steps/import.tsx
@web/lib/api.ts
@api/routers/reports.py (lines 500-569: exchanges_router POST /import endpoint)

<interfaces>
<!-- The FastAPI endpoint the frontend must call -->
From api/routers/reports.py:
```python
exchanges_router = APIRouter(prefix="/api/exchanges", tags=["exchanges"])

@exchanges_router.post("/import", response_model=ExchangeImportResponse)
async def import_exchange_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_effective_user),
    pool=Depends(get_pool_dep),
):
    # Accepts multipart form upload with field name "file"
    # Returns: { job_id: int, file_import_id: int, status: "queued" }
```

From web/lib/api.ts:
```typescript
const _raw = process.env.NEXT_PUBLIC_API_URL || '';
export const API_URL = _raw === '__RELATIVE__' ? '' : _raw;
// Note: apiClient sets Content-Type: application/json — cannot use for FormData uploads.
// Use raw fetch() with API_URL prefix instead.
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix upload URL and add API_URL prefix in import.tsx</name>
  <files>web/app/onboarding/steps/import.tsx</files>
  <action>
In `web/app/onboarding/steps/import.tsx`:

1. Add import at top: `import { API_URL } from '@/lib/api';`

2. In the `uploadFile` callback (line 39), change the fetch call from:
   ```
   const res = await fetch('/api/upload-file', {
     method: 'POST',
     credentials: 'include',
     body: formData,
   });
   ```
   To:
   ```
   const res = await fetch(`${API_URL}/api/exchanges/import`, {
     method: 'POST',
     credentials: 'include',
     body: formData,
   });
   ```

Key points:
- Do NOT set Content-Type header — the browser must auto-set it to `multipart/form-data` with the correct boundary for FormData.
- Do NOT use `apiClient` — it hardcodes `Content-Type: application/json` which breaks file uploads.
- The form field name `'file'` in `formData.append('file', file)` already matches the FastAPI `file: UploadFile = File(...)` parameter name.
  </action>
  <verify>
    <automated>cd /home/vitalpointai/projects/Axiom && grep -n "api/exchanges/import" web/app/onboarding/steps/import.tsx && grep -n "API_URL" web/app/onboarding/steps/import.tsx && ! grep -n "upload-file" web/app/onboarding/steps/import.tsx</automated>
  </verify>
  <done>The fetch URL is `${API_URL}/api/exchanges/import`, API_URL is imported from @/lib/api, and no references to the old `/api/upload-file` path remain.</done>
</task>

</tasks>

<verification>
- `grep -rn "upload-file" web/` returns zero matches (old URL fully removed)
- `grep -n "api/exchanges/import" web/app/onboarding/steps/import.tsx` shows the correct endpoint
- `grep -n "API_URL" web/app/onboarding/steps/import.tsx` confirms the import and usage
</verification>

<success_criteria>
- Onboarding step 3 file upload POSTs to `/api/exchanges/import` with API_URL prefix
- No references to `/api/upload-file` remain in the codebase frontend
- FormData upload preserves multipart/form-data content type (no explicit Content-Type header)
</success_criteria>

<output>
After completion, create `.planning/quick/2-fix-exchange-file-upload-404-in-onboardi/2-SUMMARY.md`
</output>
