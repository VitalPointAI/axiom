# Phase 7: Web UI - Research

**Researched:** 2026-03-13
**Domain:** FastAPI backend + Next.js 16 frontend integration, WebAuthn/OAuth auth migration Python
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Build a **FastAPI backend** as the single API layer replacing all Next.js API routes
- Next.js becomes a pure frontend (SSR/CSR) calling FastAPI endpoints
- FastAPI runs as its own Docker container (separate from indexer), sharing PostgreSQL
- All business logic centralized in Python — no more dual JS/Python data access
- Move all auth to FastAPI — passkey/WebAuthn registration and login handled server-side in Python
- Three auth methods all active via `@vitalpoint/near-phantom-auth`:
  1. Passkey/WebAuthn — existing flow, migrated to Python
  2. Email magic link — signup and login via email
  3. Google OAuth — via near-phantom-auth OAuth flow
- All three methods are first-class and equal — email and NEAR passkey are both valid identity anchors
- NEAR wallet is just another tracked wallet, not the identity anchor
- Users can use the system without a NEAR wallet
- Session management in PostgreSQL (existing sessions table pattern)
- Accountant access model preserved: `neartax_viewing_as` cookie + `accountant_access` table permission checks
- **Full auto-chain pipeline:** add wallet → index → classify → ACB → verify
- **Stage progress bar** showing pipeline stages: Indexing (45%) → Classifying → Cost Basis → Verifying → Done
- **Incremental + selective recalc** when adding a new wallet after initial setup
- **Inline data previews** for each report tab (first N rows from DB queries)
- Report generation via **job queue + polling**
- Generated reports stored on server and served via FastAPI. Cached until data changes
- **Admin-only specialist override** for `needs_review` items
- **Issue-centric verification dashboard** grouped by issue type
- **Transaction classification editing** — inline editing + dedicated review queue
- **Batch recalc on save** for classification changes
- **Frontend:** Next.js 16+ with App Router, React 19, Tailwind CSS 4, shadcn/ui, Recharts
- **Backend:** FastAPI (new) replacing Next.js API routes
- **Database:** PostgreSQL only (multi-user, all tables have user_id FK)
- **Auth:** near-phantom-auth (passkey + email + Google OAuth) — moved to FastAPI
- **Deployment:** Separate Docker containers: web (Next.js), api (FastAPI), indexer (Python), postgres

### Claude's Discretion
- FastAPI route organization and middleware structure
- How to handle near-phantom-auth WebAuthn in Python (may need py_webauthn or similar)
- Polling interval and UX for job status updates
- Component refactoring needed to point at FastAPI instead of Next.js API routes
- State management approach for frontend
- Mobile responsiveness level
- Exact stage progress bar implementation

### Deferred Ideas (OUT OF SCOPE)
- Real-time price updates via WebSocket (v2)
- Mobile app (v2)
- Multi-entity support for multiple corporations (v2)
- Automated exchange API sync (v2)
- WebSocket progress updates instead of polling (enhancement)
- Tax optimization suggestions (advisory feature, not reporting)
- General business accounting beyond crypto (future milestone)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| UI-01 | Web UI with user authentication via near-phantom-auth (passkey + email + Google OAuth) | FastAPI auth layer with py_webauthn + AWS SES + Google OAuth PKCE flow |
| UI-02 | Dashboard showing portfolio summary (total holdings, value by asset, staking positions) | FastAPI /api/portfolio endpoint querying acb_snapshots + staking_events; Recharts already in frontend |
| UI-03 | Wallet management view (add/edit/remove wallets, view balances, sync status) | FastAPI /api/wallets CRUD + job creation pattern from existing Next.js API; stage progress bar via polling |
| UI-04 | Transaction ledger with filtering, search, and pagination | FastAPI /api/transactions with query params; existing transactions page already has full filter/sort/paginate UI |
| UI-05 | Transaction detail view with classification editing and notes | FastAPI PATCH /api/transactions/{id}/classification; batch recalc queue pattern |
| UI-06 | Report generation UI (select tax year, generate/download reports) | FastAPI POST /api/reports/generate creates generate_reports job; polling /api/jobs/{id}/status; serve files from output/ |
| UI-07 | Verification dashboard showing reconciliation status and flagged issues | FastAPI /api/verification querying verification_results; issue-centric grouping by diagnosis_category |
| UI-08 | Multi-user support with isolated data per NEAR account | All FastAPI queries filter by user_id from session; existing multi-user pattern across all pipeline phases |
</phase_requirements>

---

## Summary

This phase wires the existing Next.js frontend (12 dashboard pages, 25+ API routes) to a new FastAPI backend that replaces all Next.js API routes. The Python backend shares the same PostgreSQL database and models already used by Phases 1-6. The primary engineering challenge is (1) migrating auth (WebAuthn passkey + email magic link + Google OAuth) from TypeScript to Python, and (2) ensuring the frontend can call FastAPI at a different origin with proper CORS and cookie configuration.

The existing frontend code is production-quality and should be preserved almost entirely — the only code-level changes are: (a) replacing `/api/*` fetch targets with `NEXT_PUBLIC_API_URL + /api/*`, (b) removing Next.js API route files, and (c) rewiring the auth-provider to call FastAPI session endpoint. The stage progress bar, report polling, and verification dashboard are new frontend additions, but all data contracts come directly from the FastAPI endpoints.

Authentication is the highest-risk area. The existing `@vitalpoint/near-phantom-auth` library is Express/Node.js only. Python must reimplement the same WebAuthn flows using `py_webauthn` (which wraps `@simplewebauthn/server`'s cryptographic operations with the same CBOR/COSE standards). The existing challenge store (currently in-memory Maps in Next.js) moves to the PostgreSQL `challenges` table. Sessions use the same `sessions` table and `neartax_session` HTTP-only cookie pattern already in the database.

**Primary recommendation:** Build FastAPI in `api/` at project root. One router file per domain (auth, wallets, transactions, reports, verification, jobs). Reuse `db/models.py` and `indexers/db.py` connection pool. Deploy as `api` Docker service on port 8000, proxied by nginx or directly accessed by Next.js via `NEXT_PUBLIC_API_URL`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.111.1 (installed) | Python web framework | Already installed; async, OpenAPI auto-docs, Pydantic validation |
| uvicorn | 0.32.1 (installed) | ASGI server | Standard FastAPI runtime |
| SQLAlchemy | 2.0.40 (installed) | ORM + query layer | Already used by all pipeline phases; models in db/models.py |
| psycopg2-binary | ≥2.9.9 (installed) | PostgreSQL driver | Already in requirements.txt |
| pydantic | 2.11.3 (installed) | Request/response schemas | Bundled with FastAPI; v2 already installed |
| py_webauthn | ≥2.0.0 | WebAuthn server-side verification | Python port of @simplewebauthn/server; same CBOR/COSE protocol |
| itsdangerous | ≥2.1.0 | Signed tokens for magic link / OAuth state | HMAC-SHA256 token signing; well-tested |
| boto3 | ≥1.34.0 | AWS SES email sending | Same email vendor as existing Next.js `lib/email.ts` (AWS SES) |
| python-jose[cryptography] | ≥3.3.0 | JWT for magic link tokens (alternative to itsdangerous) | Industry standard; optional if using itsdangerous |
| httpx | ≥0.27.0 | Async HTTP for Google OAuth token exchange | Async-native; already in FastAPI's transitive deps |
| python-multipart | 0.0.20 (installed) | File upload support | Already installed; needed for CSV import |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| aiofiles | ≥24.0.0 | Async file serving for generated reports | Serving output/{year}_tax_package/ files |
| slowapi | ≥0.1.9 | Rate limiting middleware | FastAPI equivalent of Next.js middleware rate limiter |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| py_webauthn | webauthn (PyPI) | py_webauthn is more actively maintained and matches @simplewebauthn semantics exactly |
| itsdangerous | python-jose JWT | Both work; itsdangerous is simpler for signed tokens; JWT has richer claims if needed |
| boto3 | smtplib/sendgrid | AWS SES already configured in production (AWS credentials in .env) |

**Installation:**
```bash
pip install py_webauthn itsdangerous boto3 httpx aiofiles slowapi
```

Add to `requirements.txt`.

---

## Architecture Patterns

### Recommended Project Structure
```
api/
├── main.py              # FastAPI app factory + CORS + middleware + router mounts
├── dependencies.py      # Shared: get_db_conn(), get_current_user(), require_admin()
├── auth/
│   ├── __init__.py
│   ├── router.py        # /auth/* endpoints (passkey, magic link, OAuth, session, logout)
│   ├── passkey.py       # WebAuthn register/login flows using py_webauthn
│   ├── oauth.py         # Google OAuth PKCE flow
│   ├── magic_link.py    # Email token generation + verification
│   └── session.py       # Session create/validate/destroy (PostgreSQL sessions table)
├── routers/
│   ├── wallets.py       # GET/POST/PATCH/DELETE /api/wallets + /api/wallets/{id}/sync
│   ├── transactions.py  # GET /api/transactions + PATCH /api/transactions/{id}/classification
│   ├── portfolio.py     # GET /api/portfolio/summary
│   ├── reports.py       # POST /api/reports/generate + GET /api/reports/download/{year}
│   ├── verification.py  # GET /api/verification/summary + /api/verification/issues
│   ├── jobs.py          # GET /api/jobs/{id}/status + GET /api/jobs/active
│   ├── staking.py       # GET /api/staking/positions + /api/staking/income
│   ├── exchanges.py     # GET /api/exchanges + POST /api/exchanges/import
│   └── admin.py         # Admin-only endpoints
└── schemas/
    ├── auth.py          # RegisterRequest, LoginRequest, SessionResponse
    ├── wallets.py       # WalletCreate, WalletResponse, SyncStatusResponse
    ├── transactions.py  # TransactionResponse, ClassificationUpdate
    ├── reports.py       # ReportRequest, ReportJobResponse
    └── verification.py  # IssueGroup, VerificationSummary
```

### Pattern 1: Dependency Injection for Auth
**What:** FastAPI's `Depends()` system for session validation and user injection
**When to use:** Every protected route — eliminates per-route auth boilerplate

```python
# Source: FastAPI official docs - https://fastapi.tiangolo.com/tutorial/dependencies/
# api/dependencies.py
from fastapi import Cookie, Depends, HTTPException, status
from indexers.db import get_pool

async def get_current_user(
    neartax_session: str | None = Cookie(default=None),
    pool = Depends(get_pool_dep),
) -> dict:
    if not neartax_session:
        raise HTTPException(status_code=401, detail="Authentication required")
    conn = pool.getconn()
    try:
        row = conn.execute(
            """SELECT s.user_id, u.near_account_id, u.is_admin
               FROM sessions s JOIN users u ON s.user_id = u.id
               WHERE s.id = %s AND s.expires_at > NOW()""",
            (neartax_session,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Session expired")
        return {"user_id": row[0], "near_account_id": row[1], "is_admin": row[2]}
    finally:
        pool.putconn(conn)

async def get_effective_user(
    user = Depends(get_current_user),
    neartax_viewing_as: str | None = Cookie(default=None),
    pool = Depends(get_pool_dep),
) -> dict:
    """Handles accountant 'viewing as' mode — same pattern as Next.js getAuthenticatedUser()."""
    if neartax_viewing_as:
        client_id = int(neartax_viewing_as)
        # verify accountant_access table
        ...
        return {...client_context, "actual_user_id": user["user_id"]}
    return user
```

### Pattern 2: WebAuthn Migration with py_webauthn
**What:** Reimplement `@simplewebauthn/server` flows in Python using `py_webauthn`
**When to use:** Passkey register and login endpoints

```python
# Source: py_webauthn docs - https://github.com/duo-labs/py_webauthn
import webauthn
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
)

# Register start — equivalent to createRegistrationOptions()
def start_registration(username: str, user_id_bytes: bytes) -> dict:
    options = webauthn.generate_registration_options(
        rp_id=settings.RP_ID,
        rp_name=settings.RP_NAME,
        user_id=user_id_bytes,
        user_name=username,
        user_display_name=username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
        ),
    )
    # Store challenge in PostgreSQL challenges table (not in-memory Map)
    challenge_id = str(uuid4())
    store_challenge(challenge_id, options.challenge, "registration", expires_in=60)
    return {"challengeId": challenge_id, "options": options_to_json(options)}

# Register finish — equivalent to verifyRegistration()
def finish_registration(challenge_id: str, response: dict, username: str):
    challenge_data = get_challenge(challenge_id)  # from PostgreSQL
    verification = webauthn.verify_registration_response(
        credential=response,
        expected_challenge=challenge_data.challenge,
        expected_origin=settings.ORIGIN,
        expected_rp_id=settings.RP_ID,
    )
    # Store credential_id + public_key + counter in passkeys table
    ...
```

**Critical note:** The `py_webauthn` library (duo-labs/py_webauthn) uses the same CBOR/COSE encoding as `@simplewebauthn/server`. Existing passkeys registered via the Next.js app WILL work with the Python verification — the cryptographic protocol is identical. The credential_id, public_key BYTEA, and counter values in the database remain valid.

### Pattern 3: CORS + Cookie Cross-Origin Configuration
**What:** FastAPI CORS middleware must allow credentials from Next.js origin
**When to use:** Required because Next.js and FastAPI run on different ports/domains

```python
# Source: FastAPI CORS docs - https://fastapi.tiangolo.com/tutorial/cors/
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3003",  # dev
        "https://neartax.vitalpoint.ai",  # prod
    ],
    allow_credentials=True,  # CRITICAL: required for cookies
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Next.js fetch calls** must include `credentials: "include"` to send the HTTP-only session cookie cross-origin. The existing `auth-provider.tsx` already uses `credentials: "include"` for session checks — all other fetch calls in dashboard pages need this added.

### Pattern 4: Job Creation → Pipeline Auto-chain
**What:** FastAPI creates indexing_jobs rows; IndexerService picks them up
**When to use:** Wallet add (triggers full pipeline), classification edit (triggers ACB recalc)

```python
# FastAPI wallet creation triggers full pipeline
def create_wallet_and_queue_pipeline(user_id: int, account_id: str, chain: str, conn):
    # 1. Insert wallet
    wallet_id = insert_wallet(conn, user_id, account_id, chain)

    # 2. Queue jobs in priority order (same pattern as Phase 1 plan 01-04)
    if chain == "NEAR":
        insert_job(conn, wallet_id, user_id, "full_sync", priority=10)
        insert_job(conn, wallet_id, user_id, "staking_sync", priority=8)
        insert_job(conn, wallet_id, user_id, "lockup_sync", priority=7)
    elif chain in ("ethereum", "polygon", "optimism", "cronos"):
        insert_job(conn, wallet_id, user_id, "evm_full_sync", priority=10)

    # 3. classify_transactions, calculate_acb, verify_balances auto-chain
    # via ClassifierHandler → ACBHandler → VerifyHandler (already wired in Phase 3-5)
    conn.commit()
    return wallet_id
```

**Stage progress mapping** for the progress bar UI:
- `full_sync` running = "Indexing" (0-45%)
- `classify_transactions` running = "Classifying" (45-65%)
- `calculate_acb` running = "Cost Basis" (65-85%)
- `verify_balances` running = "Verifying" (85-100%)
- All completed = "Done"

Progress within "Indexing" stage: use `progress_fetched / progress_total` from the `full_sync` job row.

### Pattern 5: Report Generation via Job Queue + Polling
**What:** FastAPI creates `generate_reports` job, frontend polls `/api/jobs/{id}/status`
**When to use:** User clicks "Generate Full Package"

```python
# POST /api/reports/generate
@router.post("/generate")
async def generate_reports(
    req: ReportRequest,
    user = Depends(get_effective_user),
    pool = Depends(get_pool_dep),
):
    conn = pool.getconn()
    try:
        # Create generate_reports job (already supported by ReportHandler in Phase 6)
        job_id = insert_job(
            conn, wallet_id=None, user_id=user["user_id"],
            job_type="generate_reports",
            cursor=json.dumps({"year": req.year, "specialist_override": req.specialist_override}),
        )
        conn.commit()
        return {"job_id": job_id, "status": "queued"}
    finally:
        pool.putconn(conn)
```

**Polling frontend pattern** (existing sync-status.tsx does 10s polling during sync, 30s idle — use same):
```typescript
// Poll every 3s for active job, stop when status == 'completed' or 'failed'
useEffect(() => {
  if (!jobId || jobStatus === 'completed' || jobStatus === 'failed') return;
  const interval = setInterval(async () => {
    const res = await fetch(`${API_URL}/api/jobs/${jobId}/status`, { credentials: 'include' });
    const data = await res.json();
    setJobStatus(data.status);
    if (data.status === 'completed') setDownloadUrl(data.download_url);
  }, 3000);
  return () => clearInterval(interval);
}, [jobId, jobStatus]);
```

### Pattern 6: Inline Classification Editing with Batch Recalc
**What:** PATCH `/api/transactions/{id}/classification` + POST `/api/transactions/apply-changes`
**When to use:** Transaction review queue and inline edit from ledger

The "Apply Changes" button creates a `calculate_acb` job for affected tokens. This is safe because:
- Classification edits are staged in `transaction_classifications` table (update tax_category + notes)
- ACB recalc reads from `transaction_classifications` (already does)
- Only tokens touched by edits need recalc (`token_symbol IN (edited_tokens)`)

### Anti-Patterns to Avoid
- **Storing challenges in FastAPI process memory:** Use PostgreSQL `challenges` table (process restarts lose in-memory state; Docker rolling restart would break active auth flows)
- **Blocking synchronous DB calls in async FastAPI routes:** Use `pool.getconn()` with `run_in_executor` or switch to asyncpg. Preferred: keep psycopg2 with `run_in_threadpool` wrapper via `fastapi.concurrency.run_in_threadpool` — matches existing pipeline pattern
- **Forwarding Next.js API routes as proxies:** Remove Next.js API routes entirely; don't create pass-through proxies — adds latency and maintenance burden
- **Rebuilding near-phantom-auth in Python from scratch:** The library's Node.js server SDK is Express-only. Only the WebAuthn cryptographic primitives need Python equivalents (py_webauthn covers this). The JavaScript client-side browser calls (navigator.credentials.create/get) are unaffected — they stay in the existing Next.js auth page
- **Setting `SameSite=Strict` on session cookies:** Cross-origin requests (Next.js → FastAPI) with `SameSite=Strict` will drop cookies. Use `SameSite=Lax` for cookie set by FastAPI; ensure `Secure=True` in production

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WebAuthn register/login | Custom CBOR parser + COSE key verifier | py_webauthn | CBOR/COSE encoding has 15+ edge cases; replay attack prevention via counter requires careful implementation |
| PKCE OAuth state CSRF protection | Custom token store | `secrets.token_urlsafe()` + PostgreSQL challenges table | State must survive process restarts; in-memory is not crash-safe |
| Rate limiting | Custom IP counter | slowapi (Starlette-native) | Thread-safe, supports burst limiting, decorator-based — identical to existing Next.js pattern |
| Email HTML templates | String concatenation | Jinja2 (already installed via FastAPI) | Already available; existing WeasyPrint PDF templates use Jinja2 |
| Signed magic link tokens | Custom HMAC | itsdangerous `URLSafeTimedSerializer` | Built-in expiry, tamper detection, well-tested |
| File serving for generated reports | Custom streaming | FastAPI `FileResponse` | Built-in; handles range requests, correct Content-Disposition headers |

**Key insight:** The hardest part is not writing code — it's ensuring existing passkeys (stored credential_ids and public_keys in the database) continue to work after migrating auth to Python. `py_webauthn` uses the same WebAuthn Level 2 spec and the same binary encoding, so existing credentials are fully compatible.

---

## Common Pitfalls

### Pitfall 1: Session Cookie Cross-Origin Blocked
**What goes wrong:** Next.js on port 3003 calls FastAPI on port 8000; browser drops `neartax_session` cookie because `SameSite=Strict`
**Why it happens:** Cookies default to `SameSite=Lax` but `Secure` + cross-origin combination requires explicit configuration
**How to avoid:** FastAPI sets cookie with `samesite="lax"`, `httponly=True`, `secure=True` (prod) / `secure=False` (dev). Next.js fetches use `credentials: "include"`. CORS `allow_credentials=True` + explicit `allow_origins` (not `*`).
**Warning signs:** 401 responses on all authenticated requests despite being logged in

### Pitfall 2: WebAuthn Origin Mismatch
**What goes wrong:** Passkey login fails with "origin mismatch" error after migrating to FastAPI
**Why it happens:** WebAuthn verifies the `origin` claim in the authenticator data against `expected_origin`. If FastAPI sets `ORIGIN=https://neartax.vitalpoint.ai` but the passkey was registered with `origin=https://neartax.vitalpoint.ai`, they must match exactly (including protocol and port).
**How to avoid:** Keep `RP_ID` and `ORIGIN` config values identical to what was used during registration (stored in the existing `passkeys` table rows). No migration needed — just read correct values from env.
**Warning signs:** "authenticatorData.rpIdHash does not match expected RP ID hash"

### Pitfall 3: psycopg2 Blocking in Async FastAPI
**What goes wrong:** Slow DB queries block the FastAPI event loop; concurrent requests queue up
**Why it happens:** psycopg2 is synchronous; calling it directly in `async def` handlers blocks the event loop
**How to avoid:** Use `await run_in_threadpool(db_func, ...)` from `fastapi.concurrency` for any psycopg2 call, OR switch to `asyncpg`. Since the entire pipeline uses psycopg2 + `get_pool()`, use `run_in_threadpool` to avoid a driver split.
**Warning signs:** CPU=0% but requests timing out; single request blocks all others

### Pitfall 4: Auth Tables Missing from Alembic Migrations
**What goes wrong:** FastAPI starts but crashes because `sessions`, `passkeys`, `users.username`, `users.email`, `users.is_admin` columns don't exist in PostgreSQL schema
**Why it happens:** These tables were created ad-hoc by the Next.js app's route handlers (`CREATE TABLE IF NOT EXISTS`) — not via Alembic migrations
**How to avoid:** Create migration `006_auth_schema.py` that formalizes `users` (add `username`, `email`, `is_admin`, `codename` columns), `passkeys`, `sessions`, `accountant_access`, `magic_link_tokens`, `challenges` tables. Must run before FastAPI starts.
**Warning signs:** `psycopg2.errors.UndefinedTable: relation "passkeys" does not exist`

### Pitfall 5: Next.js API Routes Still Active in Production
**What goes wrong:** Both Next.js API routes and FastAPI endpoints respond; frontend hits different backends depending on path
**Why it happens:** Removing Next.js API route files one-by-one is error-prone; easy to miss routes
**How to avoid:** Delete the entire `web/app/api/` directory in a single wave after FastAPI equivalents are verified. Keep a transition period where both exist only during development/testing.
**Warning signs:** Some requests return JSON from Python format, others from TypeScript format

### Pitfall 6: Report Download URL Construction
**What goes wrong:** FastAPI serves report files but Next.js constructs wrong URL (uses `/api/reports/download` pointing to old Next.js route)
**Why it happens:** Frontend hardcodes API path without `NEXT_PUBLIC_API_URL` prefix
**How to avoid:** All fetch calls in Next.js pages must use `${process.env.NEXT_PUBLIC_API_URL}/api/...` not `/api/...`
**Warning signs:** 404 on report download after generation appears to complete

### Pitfall 7: Accountant Viewing Mode Context Loss
**What goes wrong:** FastAPI reads `neartax_viewing_as` cookie but applies session user's `user_id` to queries instead of client's `user_id`
**Why it happens:** The `get_effective_user()` dependency must be used (not `get_current_user()`) on all data endpoints that accountants can access via client-switching
**How to avoid:** All data routers (wallets, transactions, portfolio, reports, verification) use `get_effective_user()`. Only admin endpoints use `get_current_user()` + admin check.
**Warning signs:** Accountant sees their own data when switching to a client

---

## Code Examples

### FastAPI App Factory
```python
# Source: FastAPI official docs
# api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.auth.router import router as auth_router
from api.routers.wallets import router as wallets_router
from api.routers.transactions import router as transactions_router
from api.routers.portfolio import router as portfolio_router
from api.routers.reports import router as reports_router
from api.routers.verification import router as verification_router
from api.routers.jobs import router as jobs_router

def create_app() -> FastAPI:
    app = FastAPI(title="Axiom API", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,  # ["http://localhost:3003", "https://neartax.vitalpoint.ai"]
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(wallets_router, prefix="/api/wallets", tags=["wallets"])
    app.include_router(transactions_router, prefix="/api/transactions", tags=["transactions"])
    app.include_router(portfolio_router, prefix="/api/portfolio", tags=["portfolio"])
    app.include_router(reports_router, prefix="/api/reports", tags=["reports"])
    app.include_router(verification_router, prefix="/api/verification", tags=["verification"])
    app.include_router(jobs_router, prefix="/api/jobs", tags=["jobs"])

    return app

app = create_app()
```

### Session Cookie Pattern (FastAPI)
```python
# Source: FastAPI response/cookies docs
# Mirrors existing Next.js createSession() in web/lib/auth.ts
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Response

def create_session(user_id: int, response: Response, conn) -> str:
    session_id = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    conn.execute(
        "INSERT INTO sessions (id, user_id, expires_at) VALUES (%s, %s, %s)",
        (session_id, user_id, expires_at)
    )
    response.set_cookie(
        key="neartax_session",
        value=session_id,
        httponly=True,
        secure=True,   # False in dev
        samesite="lax",
        max_age=7 * 24 * 3600,
        domain=settings.COOKIE_DOMAIN,  # ".vitalpoint.ai" for prod
    )
    return session_id
```

### Sync Status Aggregation Query
```python
# Mirrors existing web/app/api/sync/status/route.ts logic
# Used by GET /api/jobs/active and wallet sync status
SYNC_STATUS_QUERY = """
SELECT
    w.id as wallet_id,
    w.account_id,
    CASE
        WHEN EXISTS (SELECT 1 FROM indexing_jobs ij WHERE ij.wallet_id = w.id AND ij.status = 'running') THEN 'syncing'
        WHEN EXISTS (SELECT 1 FROM indexing_jobs ij WHERE ij.wallet_id = w.id AND ij.status IN ('queued','retrying')) THEN 'pending'
        WHEN EXISTS (SELECT 1 FROM indexing_jobs ij WHERE ij.wallet_id = w.id AND ij.status = 'failed') THEN 'error'
        WHEN EXISTS (SELECT 1 FROM indexing_jobs ij WHERE ij.wallet_id = w.id AND ij.status = 'completed') THEN 'synced'
        ELSE 'pending'
    END as sync_status,
    (SELECT MAX(completed_at) FROM indexing_jobs WHERE wallet_id = w.id AND status = 'completed') as last_synced_at,
    (SELECT progress_fetched FROM indexing_jobs WHERE wallet_id = w.id AND job_type = 'full_sync' ORDER BY created_at DESC LIMIT 1) as progress_fetched,
    (SELECT progress_total FROM indexing_jobs WHERE wallet_id = w.id AND job_type = 'full_sync' ORDER BY created_at DESC LIMIT 1) as progress_total
FROM wallets w
WHERE w.user_id = %s
ORDER BY w.created_at DESC
"""
```

### Pipeline Stage Progress Calculation
```python
# For the stage progress bar: Indexing → Classifying → Cost Basis → Verifying → Done
def get_pipeline_stage(wallet_id: int, conn) -> dict:
    jobs = conn.execute(
        """SELECT job_type, status, progress_fetched, progress_total
           FROM indexing_jobs WHERE wallet_id = %s
           ORDER BY created_at DESC""",
        (wallet_id,)
    ).fetchall()

    job_map = {row["job_type"]: row for row in jobs}

    stages = [
        ("full_sync",              "Indexing",    0,  45),
        ("classify_transactions",  "Classifying", 45, 65),
        ("calculate_acb",          "Cost Basis",  65, 85),
        ("verify_balances",        "Verifying",   85, 100),
    ]

    for job_type, label, pct_start, pct_end in stages:
        job = job_map.get(job_type)
        if not job or job["status"] == "queued":
            return {"stage": label, "pct": pct_start, "detail": "Waiting..."}
        if job["status"] == "running":
            if job["progress_total"] and job["progress_total"] > 0:
                inner_pct = job["progress_fetched"] / job["progress_total"]
                pct = pct_start + inner_pct * (pct_end - pct_start)
                detail = f"{job['progress_fetched']:,} of {job['progress_total']:,} transactions"
            else:
                pct = pct_start
                detail = "Processing..."
            return {"stage": label, "pct": round(pct), "detail": detail}

    return {"stage": "Done", "pct": 100, "detail": "Pipeline complete"}
```

### Next.js API URL Migration Pattern
```typescript
// Before (Next.js API route):
const res = await fetch('/api/wallets');

// After (FastAPI backend):
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const res = await fetch(`${API_URL}/api/wallets`, { credentials: 'include' });
```

Add `NEXT_PUBLIC_API_URL=http://api:8000` to Next.js Docker service environment (internal Docker network).
Add `NEXT_PUBLIC_API_URL=https://api.neartax.vitalpoint.ai` for production (or proxy via nginx).

### Google OAuth Flow (Python)
```python
# Mirrors existing web/app/api/phantom-auth/oauth/start/route.ts
import secrets
import httpx
from urllib.parse import urlencode

async def start_google_oauth(response: Response, conn) -> dict:
    state = secrets.token_urlsafe(32)
    # Store state in challenges table (not cookie — FastAPI has no Next.js cookies() API)
    store_challenge(conn, state, challenge_type="oauth_state", expires_in=600)

    params = urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    })
    return {"authUrl": f"https://accounts.google.com/o/oauth2/v2/auth?{params}"}

async def finish_google_oauth(code: str, state: str, response: Response, conn) -> dict:
    # Verify state from challenges table
    verify_challenge(conn, state, challenge_type="oauth_state")

    async with httpx.AsyncClient() as client:
        token_res = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.OAUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        tokens = token_res.json()
        user_res = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        user_info = user_res.json()

    # Upsert user (by email), create session
    user_id = upsert_oauth_user(conn, user_info["email"], user_info.get("name"))
    create_session(user_id, response, conn)
    return {"success": True}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Next.js API routes as backend | FastAPI as dedicated backend | Phase 7 | Python-only business logic; eliminates TypeScript DB queries |
| SQLite (neartax.db) | PostgreSQL only | Phase 1 | Multi-user isolation; concurrent indexer + API access |
| In-memory challenge store (Map) | PostgreSQL challenges table | Phase 7 | Crash-safe; works across multiple FastAPI workers |
| @vitalpoint/near-phantom-auth Node.js SDK | py_webauthn Python server | Phase 7 | Same WebAuthn spec; existing credentials remain valid |
| NEAR wallet as identity anchor | Email/passkey as identity anchor | Phase 7 decision | Users without NEAR can use system (EVM/exchange-only users) |

**Deprecated/outdated in this phase:**
- `web/app/api/` directory: entire Next.js API routes directory is deleted after FastAPI is wired
- `web/lib/db.ts`: Next.js DB connection pool removed; FastAPI uses `indexers/db.py` pattern
- `web/lib/auth.ts`: Replaced by FastAPI `api/auth/` module
- `web/middleware.ts`: Rate limiting + auth middleware replaced by FastAPI middleware (`slowapi` + `dependencies.py`)

---

## Auth Migration Deep-Dive

### What `@vitalpoint/near-phantom-auth` Does vs. What Python Needs

The library provides:
1. **Client side (`/client`):** Browser-side `startRegistration()` / `startAuthentication()` wrappers around `navigator.credentials.create/get`. These are JavaScript-only and stay in the Next.js auth page unchanged.
2. **Server side (`/webauthn`):** `createRegistrationOptions()`, `verifyRegistration()`, `createAuthenticationOptions()`, `verifyAuthentication()`. These are thin wrappers around `@simplewebauthn/server` v13.

Python equivalents via `py_webauthn`:
- `createRegistrationOptions()` → `webauthn.generate_registration_options()`
- `verifyRegistration()` → `webauthn.verify_registration_response()`
- `createAuthenticationOptions()` → `webauthn.generate_authentication_options()`
- `verifyAuthentication()` → `webauthn.verify_authentication_response()`

**Credential compatibility:** The `credential_id` (base64url TEXT), `public_key` (BYTEA), and `counter` (INTEGER) stored in the `passkeys` table are spec-compliant WebAuthn values. `py_webauthn` reads and writes them in the same format.

### Auth Schema Requirements (Migration 006)

The existing Next.js app creates these tables ad-hoc. Alembic migration `006_auth_schema.py` must formalize them:

```sql
-- Users table additions (existing table needs columns added)
ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(128) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(256) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS codename VARCHAR(64) UNIQUE;

-- Passkeys (WebAuthn credentials)
CREATE TABLE IF NOT EXISTS passkeys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    credential_id TEXT UNIQUE NOT NULL,
    public_key BYTEA NOT NULL,
    counter BIGINT NOT NULL DEFAULT 0,
    device_type TEXT,
    backed_up BOOLEAN DEFAULT FALSE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Sessions
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,  -- secrets.token_hex(32)
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

-- WebAuthn challenges (replaces in-memory Map)
CREATE TABLE IF NOT EXISTS challenges (
    id TEXT PRIMARY KEY,
    challenge BYTEA NOT NULL,
    challenge_type TEXT NOT NULL,  -- 'registration', 'authentication', 'oauth_state'
    user_id INTEGER REFERENCES users(id),
    expires_at TIMESTAMPTZ NOT NULL,
    metadata JSONB
);
CREATE INDEX IF NOT EXISTS idx_challenges_expires ON challenges(expires_at);

-- Magic link tokens
CREATE TABLE IF NOT EXISTS magic_link_tokens (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Accountant access
CREATE TABLE IF NOT EXISTS accountant_access (
    id SERIAL PRIMARY KEY,
    accountant_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_level TEXT NOT NULL CHECK (permission_level IN ('read', 'readwrite')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(accountant_user_id, client_user_id)
);
```

---

## Docker Integration

### New `api` Service in docker-compose.prod.yml

```yaml
api:
  build:
    context: .
    dockerfile: api/Dockerfile
  ports:
    - "8000:8000"
  environment:
    - DATABASE_URL=postgresql://neartax:${POSTGRES_PASSWORD}@postgres:5432/neartax
    - RP_ID=${RP_ID:-neartax.vitalpoint.ai}
    - RP_NAME=${RP_NAME:-Axiom}
    - ORIGIN=${ORIGIN:-https://neartax.vitalpoint.ai}
    - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
    - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
    - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
    - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
    - AWS_SES_REGION=${AWS_SES_REGION:-ca-central-1}
    - ALLOWED_ORIGINS=https://neartax.vitalpoint.ai,http://localhost:3003
    - SESSION_SECURE=true
  depends_on:
    postgres:
      condition: service_healthy
    migrate:
      condition: service_completed_successfully
  command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
```

**Next.js web service** needs one new env var:
```yaml
- NEXT_PUBLIC_API_URL=http://api:8000  # internal Docker network
```

For production with nginx reverse proxy: `NEXT_PUBLIC_API_URL=https://neartax.vitalpoint.ai` with nginx routing `/api/*` and `/auth/*` to the FastAPI container.

### api/Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Uses project root as build context (same as indexers/Dockerfile pattern) so `db/models.py`, `config.py`, `indexers/db.py` are all importable.

---

## Open Questions

1. **Email magic link implementation status**
   - What we know: `web/lib/email.ts` uses AWS SES for sending (configured); no magic link routes exist in current Next.js app
   - What's unclear: Is email magic link a fully new feature or just referenced in CONTEXT.md as "should work"?
   - Recommendation: Implement as new FastAPI endpoints (`POST /auth/magic-link/request`, `GET /auth/magic-link/verify?token=...`). Standard HMAC-signed token, 15-minute expiry. AWS SES credentials are already in the environment.

2. **Accountant client-switching invite flow**
   - What we know: `accountant_access` table + `neartax_viewing_as` cookie pattern exists in Next.js code
   - What's unclear: Is there a UI for inviting accountants / requesting access? The `sendAccountantInviteEmail()` function exists in `web/lib/email.ts` but no UI was found
   - Recommendation: Include basic accountant invite API (`POST /api/accountant/invite`, `GET /api/accountant/clients`) — the data model is already there

3. **Reports inline preview data contracts**
   - What we know: The 16-tab reports page currently calls 16 different `/api/reports/*` endpoints; those Next.js routes don't exist in the codebase (missing)
   - What's unclear: The existing reports page fetches from routes that were never implemented (placeholders). FastAPI needs to implement all 16 report tab queries.
   - Recommendation: Map each tab to a FastAPI endpoint that calls the corresponding Phase 6 report module. For inline preview, limit to 50 rows and return as JSON; for download, call PackageBuilder.

4. **Nginx routing vs. dual-port access**
   - What we know: Production currently has Next.js on port 3003; no nginx config was found in the repo
   - What's unclear: How will the browser reach FastAPI in production — separate subdomain (`api.neartax.vitalpoint.ai`), nginx proxy at same domain, or separate port?
   - Recommendation: Add nginx service to docker-compose routing `/auth/*` and `/api/*` to FastAPI, everything else to Next.js. This avoids `NEXT_PUBLIC_API_URL` cross-origin complexity in production.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (already used in tests/ for all phases) |
| Config file | none — run directly |
| Quick run command | `python -m pytest tests/test_api_auth.py tests/test_api_wallets.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UI-01 | Passkey register/login endpoints return correct challenge/session | unit | `pytest tests/test_api_auth.py::TestPasskeyRegister -x` | ❌ Wave 0 |
| UI-01 | Google OAuth callback creates session correctly | unit | `pytest tests/test_api_auth.py::TestGoogleOAuth -x` | ❌ Wave 0 |
| UI-01 | Session cookie set with correct flags (httponly, samesite=lax) | unit | `pytest tests/test_api_auth.py::TestSessionCookie -x` | ❌ Wave 0 |
| UI-02 | Portfolio summary returns holdings + staking data for user | unit | `pytest tests/test_api_portfolio.py -x` | ❌ Wave 0 |
| UI-03 | Wallet creation queues full pipeline jobs | unit | `pytest tests/test_api_wallets.py::TestWalletCreate -x` | ❌ Wave 0 |
| UI-03 | Sync status returns stage + progress for active pipeline | unit | `pytest tests/test_api_wallets.py::TestSyncStatus -x` | ❌ Wave 0 |
| UI-04 | Transaction list returns paginated results with filters applied | unit | `pytest tests/test_api_transactions.py::TestTransactionList -x` | ❌ Wave 0 |
| UI-05 | Classification PATCH updates tax_category + queues ACB recalc | unit | `pytest tests/test_api_transactions.py::TestClassificationEdit -x` | ❌ Wave 0 |
| UI-06 | Report generate creates generate_reports job + returns job_id | unit | `pytest tests/test_api_reports.py::TestReportGenerate -x` | ❌ Wave 0 |
| UI-06 | Job status endpoint returns progress and download_url on completion | unit | `pytest tests/test_api_jobs.py -x` | ❌ Wave 0 |
| UI-07 | Verification summary returns issues grouped by diagnosis_category | unit | `pytest tests/test_api_verification.py -x` | ❌ Wave 0 |
| UI-08 | All data endpoints return only the authenticated user's data | unit | `pytest tests/test_api_auth.py::TestMultiUserIsolation -x` | ❌ Wave 0 |
| UI-08 | Accountant viewing-as mode returns client data not accountant data | unit | `pytest tests/test_api_auth.py::TestAccountantMode -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_api_auth.py -x -q` (relevant test file for that task)
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_api_auth.py` — covers UI-01, UI-08
- [ ] `tests/test_api_wallets.py` — covers UI-03
- [ ] `tests/test_api_transactions.py` — covers UI-04, UI-05
- [ ] `tests/test_api_portfolio.py` — covers UI-02
- [ ] `tests/test_api_reports.py` — covers UI-06
- [ ] `tests/test_api_jobs.py` — covers UI-06
- [ ] `tests/test_api_verification.py` — covers UI-07
- [ ] `tests/conftest.py` additions — FastAPI TestClient fixture, mock DB pool
- [ ] Migration `006_auth_schema.py` must exist before any API tests run
- [ ] Framework already installed: `pytest`, `fastapi` (has `TestClient` via `httpx`)

---

## Sources

### Primary (HIGH confidence)
- FastAPI official docs: https://fastapi.tiangolo.com/ — CORS, cookies, dependencies, file response
- py_webauthn GitHub: https://github.com/duo-labs/py_webauthn — register/login options/verify API
- @simplewebauthn/server v13: https://simplewebauthn.dev/ — existing library this phase mirrors
- Codebase direct inspection: `web/app/api/`, `web/lib/auth.ts`, `web/middleware.ts`, `web/lib/email.ts`

### Secondary (MEDIUM confidence)
- itsdangerous docs: https://itsdangerous.palletsprojects.com/ — `URLSafeTimedSerializer` for magic links
- slowapi GitHub: https://github.com/laurentS/slowapi — FastAPI rate limiting

### Tertiary (LOW confidence)
- Production nginx routing pattern — not verified against actual server config (no nginx.conf in repo)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — FastAPI 0.111.1, uvicorn 0.32.1, pydantic 2.11.3, sqlalchemy 2.0.40 all verified installed; py_webauthn installability verified
- Architecture: HIGH — All patterns derived from direct inspection of existing Next.js routes and Python pipeline code
- Auth migration: HIGH — `@vitalpoint/near-phantom-auth` TypeScript declarations read directly; WebAuthn compatibility confirmed via protocol spec parity
- Pitfalls: HIGH — Cross-origin cookies, challenge storage, WebAuthn origin mismatch all verified from codebase inspection

**Research date:** 2026-03-13
**Valid until:** 2026-04-13 (FastAPI 0.111.x stable track; py_webauthn v2 API stable)
