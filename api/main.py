"""Axiom FastAPI application factory.

Creates and configures the FastAPI app with:
  - CORS middleware (origins from ALLOWED_ORIGINS env var)
  - Startup/shutdown lifespan events for DB pool management
  - Router mounts for auth, wallets, transactions, portfolio, reports, verification, jobs
  - GET /health endpoint

Usage::

    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

import indexers.db as _db
from api.rate_limit import limiter
from config import validate_env, OFFLINE_MODE
from api.auth import router as auth_router
from api.routers import (
    accountant_router,
    admin_router,
    assets_router,
    audit_router,
    exchanges_router,
    jobs_router,
    portfolio_router,
    preferences_router,
    reports_router,
    staking_router,
    streaming_router,
    transactions_router,
    verification_router,
    waitlist_router,
    wallets_router,
)


# ---------------------------------------------------------------------------
# Lifespan: DB pool init and teardown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize the psycopg2 connection pool on startup, close on shutdown."""
    validate_env()
    _db.get_pool()
    yield
    _db.close_pool()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    application = FastAPI(
        title="Axiom API",
        version="1.0.0",
        description=(
            "FastAPI backend for Axiom — NEAR & multi-chain crypto tax reporting. "
            "Serves the Next.js UI and provides all data, auth, and job queue endpoints."
        ),
        lifespan=lifespan,
    )

    # ----------------------------------------------------------------
    # Rate limiting (slowapi)
    # ----------------------------------------------------------------
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ----------------------------------------------------------------
    # CORS middleware
    # Origins from ALLOWED_ORIGINS env var (comma-separated list).
    # Defaults to localhost dev origins for safety.
    # ----------------------------------------------------------------
    raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # ----------------------------------------------------------------
    # Router mounts
    # ----------------------------------------------------------------
    application.include_router(auth_router)
    application.include_router(wallets_router)
    application.include_router(assets_router)
    application.include_router(transactions_router)
    application.include_router(portfolio_router)
    application.include_router(reports_router)
    application.include_router(exchanges_router)
    application.include_router(verification_router)
    application.include_router(jobs_router)
    application.include_router(audit_router)
    application.include_router(accountant_router)
    application.include_router(preferences_router)
    application.include_router(staking_router)
    application.include_router(waitlist_router)
    application.include_router(streaming_router, prefix="/api/stream")
    application.include_router(admin_router, prefix="/api/admin")

    # ----------------------------------------------------------------
    # Health check — unauthenticated
    # ----------------------------------------------------------------
    @application.get("/health", tags=["health"])
    def health_check() -> dict:
        """Return API health status. Used by load balancers and Docker health checks.

        Includes offline_mode from config so UI and monitoring can detect
        when network-dependent indexer jobs are being held back.
        """
        return {
            "status": "ok",
            "offline_mode": OFFLINE_MODE,
            "database": "ok",
        }

    # ----------------------------------------------------------------
    # Status endpoint — offline mode + system info
    # ----------------------------------------------------------------
    @application.get("/api/status", tags=["health"])
    def api_status() -> dict:
        """Return system status including offline_mode configuration."""
        return {
            "offline_mode": OFFLINE_MODE,
            "database": "ok",
            "status": "ok",
        }

    return application


# Module-level app instance for uvicorn and pytest TestClient
app = create_app()
