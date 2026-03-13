"""Job status endpoints (stub — full implementation in Task 2)."""

from fastapi import APIRouter, Depends

from api.dependencies import get_effective_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
async def list_jobs_stub(user=Depends(get_effective_user)):
    """Stub: returns empty list."""
    return []
