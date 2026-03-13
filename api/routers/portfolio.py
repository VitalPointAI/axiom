"""Portfolio summary endpoint (stub — full implementation in Task 2)."""

from fastapi import APIRouter, Depends

from api.dependencies import get_effective_user

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("")
async def get_portfolio_stub(user=Depends(get_effective_user)):
    """Stub: returns empty dict."""
    return {}
