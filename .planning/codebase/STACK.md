# Technology Stack

**Analysis Date:** 2026-03-13

## Languages

**Primary:**
- TypeScript 5.9.3 - Next.js frontend, React components, type-safe client code
- Python 3.11 - FastAPI backend, indexers, database operations

**Secondary:**
- JavaScript (Node.js scripts) - Legacy scripts and analysis tools in project root

## Runtime

**Environment:**
- Node.js 20 (Alpine) - Frontend runtime and build
- Python 3.11 (slim) - Backend API and indexer processes
- PostgreSQL 16 - Production database

**Package Managers:**
- npm - Node.js dependencies (web/)
- pip - Python dependencies (requirements.txt, indexers/requirements.txt)
- Lockfiles present: package-lock.json (npm), no pip lockfile

## Frameworks

**Core:**
- Next.js 16.1.6 - Server-side rendering, API middleware, production deployment
- FastAPI 0.111.0 - REST API backend, async HTTP handling, automatic OpenAPI docs
- React 19.2.4 - Component framework for web UI

**UI & Styling:**
- Tailwind CSS 4.2.1 - Utility-first styling
- Headless UI - Unstyled accessible components
- Lucide React 0.469.0 - Icon library
- Recharts 2.15.0 - Data visualization charts

**Testing:**
- pytest - Assumed (FastAPI standard, no explicit test config found)
- httpx 0.27.0 - HTTP client for async testing

**Build/Dev:**
- Webpack - Next.js bundler (configured in build scripts)
- ESLint 8.57.0 - JavaScript linting
- PostCSS 8.5.6 - CSS transformation

## Key Dependencies

**Critical:**
- psycopg2-binary 2.9.9 - PostgreSQL adapter (primary data store)
- SQLAlchemy 2.0.0 - ORM for database migrations and queries via Alembic
- Alembic 1.13.0 - Database versioning and migrations
- FastAPI 0.111.0 + uvicorn 0.29.0 - Production HTTP server

**Authentication & Security:**
- webauthn 2.0.0 - WebAuthn/passkey support (server-side verification)
- @simplewebauthn/server 13.2.3 - WebAuthn ceremony utilities
- @simplewebauthn/browser 13.2.2 - WebAuthn client-side helpers
- itsdangerous 2.1.0 - Signed token generation (magic links)
- boto3 1.34.0 - AWS SES for email delivery

**Infrastructure:**
- aiohttp 3.9.0 - Async HTTP client for external APIs
- requests 2.31.0 - Synchronous HTTP client (fallback)
- better-sqlite3 11.0.0 - SQLite client for web (legacy or sync use)
- pg 8.19.0 - PostgreSQL client (web frontend direct DB access, if used)

**Blockchain/Crypto:**
- @aurora-is-near/intents-swap-widget 6.3.1 - NEAR Protocol DEX widget
- @vitalpoint/near-phantom-auth 0.5.2 - Custom NEAR authentication
- @walletconnect/sign-client 2.23.6 - WalletConnect v2 integration
- algosdk - Algorand blockchain SDK (installed, minimal usage)

**PDF Processing:**
- pdf-parse 1.1.0 - Extract text from PDFs
- pdf2json 3.1.4 - PDF to JSON conversion
- pdfjs-dist 3.11.174 - PDF rendering library

**Rate Limiting & Utilities:**
- slowapi 0.1.9 - Rate limiting for FastAPI
- python-multipart 0.0.9 - Form data parsing
- python-dotenv 1.0.0 - .env file loading
- clsx 2.1.1 - Conditional classname utility

## Configuration

**Environment:**
- Configuration via .env files (not committed)
- Environment variable schema in `config.py` for Python backend
- `.env.example` provided for reference
- Next.js environment: `NEXT_PUBLIC_API_URL` for API endpoint discovery

**Build:**
- `next.config.ts` - Next.js build configuration
- `tsconfig.json` - TypeScript configuration
- `tailwind.config.ts` - Tailwind CSS customization
- `docker-compose.yml` - Development orchestration
- `docker-compose.prod.yml` - Production orchestration with resource limits
- `.prettierrc` (if present) - Code formatting
- `eslint.config.mjs` - ESLint rules

## Platform Requirements

**Development:**
- Docker & Docker Compose (recommended for consistent environment)
- Node.js 20.x
- Python 3.11+
- PostgreSQL 16 (local or containerized)

**Production:**
- Docker containerization (multi-stage builds included)
- PostgreSQL 16+
- 512M+ RAM for API/Indexer containers
- 256M+ RAM for web container
- CloudWatch/SES support (AWS Optional)

---

*Stack analysis: 2026-03-13*
