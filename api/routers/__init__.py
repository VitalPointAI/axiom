"""API data routers package.

Stub routers for wallets, transactions, portfolio, reports, verification, and jobs.
Each stub router has a GET / endpoint that requires authentication, so unauthenticated
requests return 401. Full implementations are added in later plans (07-04 through 07-07).
"""

from fastapi import APIRouter, Depends

from api.dependencies import get_effective_user

wallets_router = APIRouter(prefix="/api/wallets", tags=["wallets"])
transactions_router = APIRouter(prefix="/api/transactions", tags=["transactions"])
portfolio_router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
reports_router = APIRouter(prefix="/api/reports", tags=["reports"])
verification_router = APIRouter(prefix="/api/verification", tags=["verification"])
jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ---------------------------------------------------------------------------
# Stub endpoints — enforce auth so unauthenticated requests return 401.
# Full route handlers replace these in later plans.
# ---------------------------------------------------------------------------


@wallets_router.get("")
def list_wallets_stub(user=Depends(get_effective_user)):
    """Stub: returns empty list until 07-04 implements full wallet list."""
    return []


@transactions_router.get("")
def list_transactions_stub(user=Depends(get_effective_user)):
    """Stub: returns empty list until 07-04 implements full transaction list."""
    return []


@portfolio_router.get("")
def get_portfolio_stub(user=Depends(get_effective_user)):
    """Stub: returns empty dict until 07-05 implements portfolio summary."""
    return {}


@reports_router.get("")
def list_reports_stub(user=Depends(get_effective_user)):
    """Stub: returns empty list until 07-06 implements report endpoints."""
    return []


@verification_router.get("")
def list_verification_stub(user=Depends(get_effective_user)):
    """Stub: returns empty list until 07-06 implements verification endpoints."""
    return []


@jobs_router.get("")
def list_jobs_stub(user=Depends(get_effective_user)):
    """Stub: returns empty list until 07-07 implements job status endpoints."""
    return []
