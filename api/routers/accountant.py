"""Accountant client-switching and grant management endpoints.

Allows accountants to view their clients' data by setting/clearing
the neartax_viewing_as cookie.

Phase 16 additions (plan 16-06):
  - POST /api/accountant/grant: client grants accountant read access;
    server rewraps client's DEK with accountant's ML-KEM public key (D-25).
  - DELETE /api/accountant/access/{grant_id}: revoke a grant; wipes rewrapped DEK.
  - POST /api/accountant/sessions/materialize: internal endpoint called by
    auth-service at accountant login time — unwraps all active rewrapped_client_deks
    and stores them as session-wrapped blobs in session_client_dek_cache (D-25).
    Gated on X-Internal-Service-Token (same guard as internal_crypto router).
"""

import os
from typing import Annotated, Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

import db.crypto as _c
from api.dependencies import get_current_user, get_db_conn, get_effective_user_with_dek

router = APIRouter(prefix="/api/accountant", tags=["accountant"])


# ---------------------------------------------------------------------------
# Pool dependency helper (must be defined before route decorators reference it)
# ---------------------------------------------------------------------------


def _require_pool():
    """Return the shared psycopg2 pool."""
    from api.dependencies import get_pool_dep
    return get_pool_dep()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


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


class GrantRequest(BaseModel):
    """Client-initiated grant of accountant access."""
    accountant_email_hmac: str
    access_level: str = "read"


class MaterializeRequest(BaseModel):
    """Internal: materialize session_client_dek_cache for an accountant session.

    Called by auth-service at accountant login.  Requires the accountant's
    sealing_key (32-byte hex) so the server can unseal mlkem_sealed_dk and
    unwrap all active rewrapped_client_deks.
    """
    accountant_user_id: int
    session_id: str
    sealing_key_hex: str  # 32-byte hex — present only in auth-service internal call


# ---------------------------------------------------------------------------
# Internal service token guard (mirrors internal_crypto.py)
# ---------------------------------------------------------------------------


def _constant_time_eq(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    import hmac as _hmac
    return _hmac.compare_digest(a.encode(), b.encode())


def _require_internal_token(
    x_internal_service_token: Annotated[str | None, Header()] = None,
) -> None:
    """Dependency: reject requests that lack a valid INTERNAL_SERVICE_TOKEN header."""
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INTERNAL_SERVICE_TOKEN not configured on server",
        )
    if not x_internal_service_token or not _constant_time_eq(
        x_internal_service_token, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing internal service token",
        )


# ---------------------------------------------------------------------------
# Existing switch endpoints
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Phase 16: Grant management endpoints (D-25)
# ---------------------------------------------------------------------------


@router.post("/grant", status_code=status.HTTP_201_CREATED)
async def grant_accountant_access(
    body: GrantRequest,
    user: dict = Depends(get_effective_user_with_dek),
    pool=Depends(_require_pool),
):
    """Client grants read access to an accountant.

    The client must be the currently authenticated user (not in viewing-as mode).
    Server:
      1. Looks up the accountant by email_hmac.
      2. Reads the accountant's mlkem_ek (ML-KEM-768 public key).
      3. Calls rewrap_dek_for_grantee(client_dek, accountant_mlkem_ek) to wrap
         the client's DEK with the accountant's public key.
      4. INSERTs (or updates) an accountant_access row with rewrapped_client_dek.

    Requires the client's DEK to be in context (via get_effective_user_with_dek).
    """
    client_user_id = user["user_id"]

    # Validate access_level
    if body.access_level not in ("read", "readwrite"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="access_level must be 'read' or 'readwrite'",
        )

    # Capture client DEK before entering threadpool
    client_dek = _c.get_dek()

    def _grant(conn):
        cur = conn.cursor()
        try:
            # Look up accountant by email_hmac
            cur.execute(
                "SELECT id, mlkem_ek FROM users WHERE email_hmac = %s",
                (body.accountant_email_hmac,),
            )
            row = cur.fetchone()
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Accountant not found — they must be an Axiom user",
                )
            accountant_user_id, mlkem_ek = row
            if not mlkem_ek:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Accountant has no ML-KEM key — they must log in at least once post-upgrade",
                )
            if accountant_user_id == client_user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot grant access to yourself",
                )

            # Rewrap the client's DEK with the accountant's ML-KEM public key
            rewrapped = _c.rewrap_dek_for_grantee(client_dek, bytes(mlkem_ek))

            # INSERT or UPDATE the accountant_access row
            cur.execute(
                """
                INSERT INTO accountant_access
                    (accountant_user_id, client_user_id, permission_level, rewrapped_client_dek)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT ON CONSTRAINT uq_aa_accountant_client
                DO UPDATE SET
                    permission_level = EXCLUDED.permission_level,
                    rewrapped_client_dek = EXCLUDED.rewrapped_client_dek
                RETURNING id
                """,
                (accountant_user_id, client_user_id, body.access_level, rewrapped),
            )
            grant_id = cur.fetchone()[0]
            conn.commit()
            return {"grant_id": grant_id, "accountant_user_id": accountant_user_id}
        except HTTPException:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        result = await run_in_threadpool(_grant, conn)
    finally:
        pool.putconn(conn)

    return result


@router.delete("/access/{grant_id}", status_code=status.HTTP_200_OK)
async def revoke_accountant_access(
    grant_id: int,
    user: dict = Depends(get_current_user),
    pool=Depends(_require_pool),
):
    """Revoke an accountant access grant.

    Only the client (data owner) can revoke their own grants.
    The rewrapped_client_dek is deleted with the row — the accountant
    immediately loses access to the client's data.
    """
    client_user_id = user["user_id"]

    def _revoke(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """
                DELETE FROM accountant_access
                WHERE id = %s AND client_user_id = %s
                RETURNING id
                """,
                (grant_id, client_user_id),
            )
            deleted = cur.fetchone()
            conn.commit()
            return deleted is not None
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        found = await run_in_threadpool(_revoke, conn)
    finally:
        pool.putconn(conn)

    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grant not found or you are not the data owner",
        )
    return {"revoked": True, "grant_id": grant_id}


@router.get("/access", status_code=status.HTTP_200_OK)
async def list_accountant_grants(
    user: dict = Depends(get_current_user),
    pool=Depends(_require_pool),
):
    """List all accountant access grants created by this client.

    Returns cleartext fields only — grant_id, access_level, and the accountant's
    user_id. The rewrapped_client_dek is never returned in the response.
    """
    client_user_id = user["user_id"]

    def _list(conn):
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT aa.id, aa.accountant_user_id, aa.permission_level, aa.created_at
                FROM accountant_access aa
                WHERE aa.client_user_id = %s
                ORDER BY aa.created_at DESC
                """,
                (client_user_id,),
            )
            return cur.fetchall()
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        rows = await run_in_threadpool(_list, conn)
    finally:
        pool.putconn(conn)

    return [
        {
            "grant_id": row[0],
            "accountant_user_id": row[1],
            "access_level": row[2],
            "created_at": row[3].isoformat() if row[3] else None,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Phase 16: Accountant session materialization (internal, auth-service only)
# ---------------------------------------------------------------------------


@router.post("/sessions/materialize", status_code=status.HTTP_200_OK)
async def materialize_accountant_session(
    body: MaterializeRequest,
    _token: None = Depends(_require_internal_token),
    pool=Depends(_require_pool),
):
    """Materialize session_client_dek_cache rows for an accountant's new session.

    Called by auth-service immediately after login when the session user is an
    accountant (has active accountant_access grants as accountant_user_id).

    For each active grant:
      1. Load the rewrapped_client_dek from accountant_access.
      2. Unseal the accountant's ML-KEM dk using the provided sealing_key.
      3. Unwrap the client DEK using the accountant's ML-KEM dk.
      4. Re-wrap the client DEK with SESSION_DEK_WRAP_KEY (same format as session_dek_cache).
      5. INSERT into session_client_dek_cache (session_id, client_user_id, encrypted_client_dek, expires_at).

    This endpoint is NOT public — gated on X-Internal-Service-Token (D-27).
    The sealing_key is available only in the auth-service at login time when the
    user presents their passkey assertion (plan 16-03).
    """
    try:
        sealing_key = bytes.fromhex(body.sealing_key_hex)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sealing_key_hex must be a valid hex string",
        )
    if len(sealing_key) != 32:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sealing_key_hex must represent exactly 32 bytes",
        )

    def _materialize(conn):
        cur = conn.cursor()
        try:
            # Load accountant's sealed dk and all active grants with rewrapped_client_deks
            cur.execute(
                """
                SELECT u.mlkem_sealed_dk, aa.client_user_id, aa.rewrapped_client_dek
                FROM accountant_access aa
                JOIN users u ON u.id = aa.accountant_user_id
                WHERE aa.accountant_user_id = %s
                  AND aa.rewrapped_client_dek IS NOT NULL
                """,
                (body.accountant_user_id,),
            )
            grant_rows = cur.fetchall()

            if not grant_rows:
                return {"materialized": 0}

            # Get session expiry to match session_client_dek_cache expires_at
            cur.execute(
                "SELECT expires_at FROM sessions WHERE id = %s",
                (body.session_id,),
            )
            session_row = cur.fetchone()
            if session_row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found",
                )
            expires_at = session_row[0]

            count = 0
            for mlkem_sealed_dk, client_user_id, rewrapped_client_dek in grant_rows:
                if mlkem_sealed_dk is None or rewrapped_client_dek is None:
                    continue
                try:
                    # Unwrap client DEK using accountant's ML-KEM dk
                    client_dek = _c.unwrap_rewrapped_dek(
                        bytes(rewrapped_client_dek),
                        bytes(mlkem_sealed_dk),
                        sealing_key,
                    )
                    # Re-wrap with SESSION_DEK_WRAP_KEY for session_client_dek_cache
                    session_wrapped = _c.wrap_session_dek(client_dek)
                    _c._zero_bytes(client_dek)

                    # INSERT or REPLACE (upsert on primary key)
                    cur.execute(
                        """
                        INSERT INTO session_client_dek_cache
                            (session_id, client_user_id, encrypted_client_dek, expires_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (session_id, client_user_id)
                        DO UPDATE SET
                            encrypted_client_dek = EXCLUDED.encrypted_client_dek,
                            expires_at = EXCLUDED.expires_at
                        """,
                        (body.session_id, client_user_id, session_wrapped, expires_at),
                    )
                    count += 1
                except Exception as exc:
                    # Log and skip this grant — don't fail the whole batch
                    import logging
                    logging.getLogger(__name__).warning(
                        "Failed to materialize grant for client_user_id=%s: %s",
                        client_user_id, exc,
                    )

            conn.commit()
            return {"materialized": count}
        except HTTPException:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    conn = pool.getconn()
    try:
        result = await run_in_threadpool(_materialize, conn)
    finally:
        pool.putconn(conn)

    return result


