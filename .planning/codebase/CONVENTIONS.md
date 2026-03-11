# Coding Conventions

**Analysis Date:** 2026-03-11

## Languages

This is a dual-language codebase:
- **Python** (backend): indexers, tax engine, database scripts, CLI tools
- **TypeScript** (web frontend + API): Next.js app with React components and API routes

Conventions differ by language context. Follow the patterns for the language you are writing.

## Naming Patterns

**Python Files:**
- Use `snake_case.py` for all files: `near_indexer.py`, `cost_basis.py`, `price_fetcher.py`
- Prefix test/debug scripts with `test_`, `check_`, `verify_`, or `fix_`: `test_trace.py`, `check_weth.py`

**TypeScript Files:**
- Use `kebab-case.tsx`/`.ts` for all files: `auth-provider.tsx`, `balance-utils.ts`, `currency-context.tsx`
- Exception: `SwapWidget.tsx` uses PascalCase (inconsistency - prefer kebab-case for new files)
- Next.js conventions: `route.ts` for API routes, `page.tsx` for pages, `layout.tsx` for layouts

**Python Functions/Variables:**
- Use `snake_case` for functions and variables: `get_wallet_id()`, `total_fetched`, `acb_per_unit`
- Use `UPPER_SNAKE_CASE` for module-level constants: `RATE_LIMIT_DELAY`, `COIN_IDS`, `PROJECT_ROOT`

**Python Classes:**
- Use `PascalCase`: `ACBTracker`, `NearBlocksClient`, `EVMIndexer`, `PriceFetcher`

**TypeScript Functions/Variables:**
- Use `camelCase` for functions and variables: `getAuthenticatedUser()`, `formatCurrency()`, `walletIds`
- Use `camelCase` for API route handler functions: `GET()`, `POST()` (Next.js convention)

**TypeScript Types/Interfaces:**
- Use `PascalCase` with `interface` keyword: `AuthUser`, `WalletData`, `PortfolioData`
- Prefer `interface` over `type` for object shapes
- Inline type assertions with `as` are used frequently: `as any[]`, `as { user_id: number }`

**React Components:**
- Use `PascalCase` function names: `PortfolioSummary()`, `Sidebar()`, `AuthProvider()`
- Named exports for components: `export function Sidebar()`
- Default exports for page components: `export default function WalletsPage()`

## Code Style

**Formatting:**
- No Prettier config detected. No `.prettierrc` file exists.
- TypeScript: 2-space indentation (Next.js default)
- Python: 4-space indentation (PEP 8 default)
- ESLint configured via `web/eslint.config.mjs` using `eslint-config-next` (core-web-vitals + typescript rules)

**Linting:**
- TypeScript: ESLint with `eslint-config-next/core-web-vitals` and `eslint-config-next/typescript`
- Python: No linting tool configured (no flake8, pylint, ruff, or mypy config files)
- Run lint: `cd web && npm run lint`

**TypeScript Strictness:**
- `"strict": true` in `web/tsconfig.json`
- Target: `ES2017`, Module: `esnext`, Module resolution: `bundler`

## Import Organization

**Python:**
1. Standard library imports (`os`, `sys`, `time`, `json`, `sqlite3`)
2. Third-party imports (`requests`, `jwt`)
3. Project root path manipulation (always appears before local imports):
   ```python
   PROJECT_ROOT = Path(__file__).parent.parent
   sys.path.insert(0, str(PROJECT_ROOT))
   ```
4. Local project imports (`from db.init import get_connection`, `from config import ...`)

**TypeScript (Next.js):**
1. Next.js framework imports (`next/server`, `next/headers`, `next/navigation`)
2. React imports (`react`)
3. Third-party library imports (`lucide-react`, `recharts`)
4. Local imports using `@/` path alias (`@/lib/db`, `@/lib/auth`, `@/components/...`)

**Path Aliases:**
- `@/*` maps to `web/*` (configured in `web/tsconfig.json`)
- Use `@/lib/db` not `../../lib/db`

## Error Handling

**Python - Indexers/Scripts:**
- Use try/except with `print()` error messages (no logging framework)
- Retry with exponential backoff for HTTP requests (see `indexers/nearblocks_client.py`)
- Pattern: catch specific HTTP errors (429 rate limit), re-raise others
- Example from `indexers/nearblocks_client.py`:
  ```python
  try:
      response = requests.get(url, timeout=30)
      if response.status_code == 429:
          if retries < MAX_RETRIES:
              # exponential backoff
  ```
- Graceful import fallbacks with feature flags:
  ```python
  try:
      import jwt
      HAS_JWT = True
  except ImportError:
      HAS_JWT = False
  ```

**TypeScript - API Routes:**
- Wrap entire handler body in try/catch
- Return `NextResponse.json({ error: 'message' }, { status: code })` on errors
- Log errors with `console.error('Context:', error)`
- Always include HTTP status codes: 400 (bad input), 401 (unauthorized), 403 (forbidden), 409 (conflict), 500 (server error), 503 (unavailable)
- Standard pattern:
  ```typescript
  export async function GET() {
    try {
      const auth = await getAuthenticatedUser();
      if (!auth) {
        return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
      }
      // ... business logic ...
      return NextResponse.json({ data });
    } catch (error) {
      console.error('Descriptive context:', error);
      return NextResponse.json({ error: 'User-facing message' }, { status: 500 });
    }
  }
  ```

**TypeScript - React Components:**
- Use try/catch in async event handlers
- Log errors with `console.error()`
- Set error state via `useState<string | null>(null)`

## Logging

**Framework:** None (both Python and TypeScript use native logging)

**Python Patterns:**
- Use `print()` for all output: progress, errors, debug info
- Format: `print(f"Context: {detail}")` for progress
- No structured logging library

**TypeScript Patterns:**
- Use `console.error()` for errors in API routes
- Use `console.error()` in React components for failed fetches
- No structured logging library

## Comments

**Python:**
- Module-level docstrings on all major files (triple-quoted, descriptive):
  ```python
  """
  Transaction classifier for Canadian tax treatment.

  Classification Types:
  - income: Taxable as income (staking rewards, airdrops, mining)
  """
  ```
- Function docstrings with Args/Returns sections in key modules (`engine/acb.py`)
- Inline comments for business logic explanations
- Shebang line `#!/usr/bin/env python3` on standalone scripts

**TypeScript:**
- JSDoc-style `/** */` comments on exported functions in library code (`web/lib/db.ts`, `web/lib/auth.ts`)
- Inline comments for security notes (`// SECURITY FIX`, `// FILTERED BY USER_ID`)
- Section comments in SQL queries

## Function Design

**Python:**
- Functions are typically short (10-30 lines) in engine modules
- Standalone scripts can have longer main blocks
- Return dictionaries for structured data (not dataclasses, except in `tax/categories.py`)
- Use `if __name__ == "__main__":` for runnable scripts

**TypeScript API Routes:**
- Functions tend to be long (50-150+ lines) with inline SQL queries
- Each route file exports named HTTP method functions: `GET()`, `POST()`, `DELETE()`
- Input validation at top of function, then business logic, then response formatting

**TypeScript Components:**
- Define interfaces at top of file for component props and data shapes
- Use hooks pattern: `useState`, `useEffect`, `useCallback`
- Fetch data in `useEffect` with loading/error state pattern:
  ```typescript
  const [data, setData] = useState<Type | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { fetchData(); }, []);
  ```

## Module Design

**Python:**
- Each directory has `__init__.py` (may be empty)
- Modules expose functions and classes directly (no `__all__` usage detected)
- No barrel files or re-exports

**TypeScript:**
- Use named exports for library functions: `export function getAuthenticatedUser()`
- Use default export for the primary object in a module: `export default db`
- `web/lib/utils.ts` is a utility barrel with small helper functions
- UI components in `web/components/ui/` follow shadcn/ui patterns with `forwardRef`

## Database Access

**Python:**
- Use `sqlite3` directly via `db/init.py` helper: `get_connection()` returns connection
- Use `?` placeholders for parameterized queries
- Pattern: get connection, execute, close manually
- Some scripts hardcode DB paths instead of using config

**TypeScript:**
- Use PostgreSQL via `pg` Pool (`web/lib/db.ts`)
- Two interfaces: async `db` object (preferred) and legacy `getDb()` compatibility shim
- `db.all()`, `db.get()`, `db.run()` for queries
- Uses `?` placeholders auto-converted to `$1, $2, ...` for PostgreSQL
- The `getDb()` shim wraps `db.prepare(sql).all(params)` pattern (mimics SQLite better-sqlite3 API)

## Authentication Pattern

- All API routes that access user data must call `getAuthenticatedUser()` first
- Return 401 if not authenticated
- Use `auth.userId` to scope all database queries to the current user
- Admin routes use `getAuthenticatedAdmin()` or `requireAdmin()`
- Accountant delegation supported via `isViewingAsClient` flag

## React Component Patterns

- All client components start with `'use client';` directive
- Icons exclusively from `lucide-react`
- Styling with Tailwind CSS utility classes
- Use `cn()` from `@/lib/utils` for conditional class merging
- UI primitives in `web/components/ui/` follow shadcn/ui conventions (forwardRef, variant props, `cn()`)

---

*Convention analysis: 2026-03-11*
