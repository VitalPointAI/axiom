"""API data routers package.

Imports real router implementations as they are built. Stub routers remain
for endpoints not yet implemented, with auth-enforcing GET handlers.
"""

from fastapi import APIRouter, Depends

from api.dependencies import get_effective_user

# ---------------------------------------------------------------------------
# Real router implementations (added as each plan completes)
# ---------------------------------------------------------------------------

from api.routers.wallets import router as wallets_router  # noqa: F401 — Plan 07-03
from api.routers.portfolio import router as portfolio_router  # noqa: F401 — Plan 07-03
from api.routers.jobs import router as jobs_router  # noqa: F401 — Plan 07-03

# ---------------------------------------------------------------------------
# Stub routers (to be replaced in later plans)
# ---------------------------------------------------------------------------

transactions_router = APIRouter(prefix="/api/transactions", tags=["transactions"])
reports_router = APIRouter(prefix="/api/reports", tags=["reports"])
verification_router = APIRouter(prefix="/api/verification", tags=["verification"])


@transactions_router.get("")
def list_transactions_stub(user=Depends(get_effective_user)):
    """Stub: returns empty list until 07-04 implements full transaction list."""
    return []


@reports_router.get("")
def list_reports_stub(user=Depends(get_effective_user)):
    """Stub: returns empty list until 07-06 implements report endpoints."""
    return []


@verification_router.get("")
def list_verification_stub(user=Depends(get_effective_user)):
    """Stub: returns empty list until 07-06 implements verification endpoints."""
    return []
