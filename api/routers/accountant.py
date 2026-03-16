"""Accountant client-switching endpoints.

Allows accountants to view their clients' data by setting/clearing
the neartax_viewing_as cookie.
"""

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from api.dependencies import get_current_user, get_db_conn

router = APIRouter(prefix="/api/accountant", tags=["accountant"])


class Client(BaseModel):
    id: int
    nearAccountId: Optional[str] = None
    name: Optional[str] = None
    permissionLevel: str = "read"
    walletCount: int = 0
    lastAccessed: Optional[str] = None


class OwnAccount(BaseModel):
    id: int
    nearAccountId: Optional[str] = None
    username: Optional[str] = None


class ViewingStatus(BaseModel):
    ownAccount: OwnAccount
    isAccountant: bool
    clients: list[Client]
    currentlyViewing: Optional[Client] = None


class SwitchRequest(BaseModel):
    clientId: int


@router.get("/switch", response_model=ViewingStatus)
async def get_switch_status(
    user: dict = Depends(get_current_user),
    neartax_viewing_as: Optional[str] = Cookie(default=None),
    conn=Depends(get_db_conn),
):
    """Return accountant status: own account, clients, and current viewing target."""
    user_id = user["user_id"]

    def _query(c):
        cur = c.cursor()
        try:
            cur.execute(
                """
                SELECT
                    aa.client_user_id,
                    u.near_account_id,
                    COALESCE(u.username, u.codename, u.email) AS name,
                    aa.permission_level,
                    (SELECT COUNT(*) FROM wallets w WHERE w.user_id = aa.client_user_id) AS wallet_count
                FROM accountant_access aa
                JOIN users u ON u.id = aa.client_user_id
                WHERE aa.accountant_user_id = %s
                ORDER BY u.near_account_id
                """,
                (user_id,),
            )
            return cur.fetchall()
        finally:
            cur.close()

    rows = await run_in_threadpool(_query, conn)

    clients = [
        Client(
            id=row[0],
            nearAccountId=row[1],
            name=row[2],
            permissionLevel=row[3],
            walletCount=row[4],
        )
        for row in rows
    ]

    currently_viewing = None
    if neartax_viewing_as:
        try:
            viewing_id = int(neartax_viewing_as)
            currently_viewing = next((c for c in clients if c.id == viewing_id), None)
        except (ValueError, TypeError):
            pass

    return ViewingStatus(
        ownAccount=OwnAccount(
            id=user_id,
            nearAccountId=user.get("near_account_id"),
            username=user.get("username"),
        ),
        isAccountant=len(clients) > 0,
        clients=clients,
        currentlyViewing=currently_viewing,
    )


@router.post("/switch")
async def switch_to_client(
    body: SwitchRequest,
    response: Response,
    user: dict = Depends(get_current_user),
    conn=Depends(get_db_conn),
):
    """Switch to viewing a client's data."""
    user_id = user["user_id"]

    def _check(c):
        cur = c.cursor()
        try:
            cur.execute(
                "SELECT 1 FROM accountant_access WHERE accountant_user_id = %s AND client_user_id = %s",
                (user_id, body.clientId),
            )
            return cur.fetchone() is not None
        finally:
            cur.close()

    has_access = await run_in_threadpool(_check, conn)
    if not has_access:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this client")

    response.set_cookie(
        key="neartax_viewing_as",
        value=str(body.clientId),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,
    )
    return {"switched": True, "clientId": body.clientId}


@router.delete("/switch")
async def exit_client_view(
    response: Response,
    user: dict = Depends(get_current_user),
):
    """Exit client viewing mode and return to own account."""
    response.delete_cookie(key="neartax_viewing_as")
    return {"switched": False}
