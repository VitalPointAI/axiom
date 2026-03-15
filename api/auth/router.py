"""Auth router — all /auth/* endpoints for session, passkey, OAuth, magic link.

Mounts at /auth prefix (defined in api/auth/__init__.py).
All DB calls use run_in_threadpool() to avoid blocking the async event loop.

Endpoints:
  POST /auth/register/start    — passkey registration options
  POST /auth/register/finish   — verify credential, create user, create session
  POST /auth/login/start       — passkey authentication options
  POST /auth/login/finish      — verify assertion, create session
  GET  /auth/session           — return current user from session cookie
  POST /auth/logout            — destroy session cookie
  GET  /auth/oauth/start       — Google OAuth redirect URL
  POST /auth/oauth/callback    — exchange code for token, create session
  POST /auth/magic-link/request — send magic link email
  GET  /auth/magic-link/verify  — verify token, create session
"""

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from api.dependencies import get_current_user, get_db_conn
from api.rate_limit import limiter
from api.schemas.auth import (
    LoginFinishRequest,
    LoginStartRequest,
    MagicLinkRequest,
    OAuthCallbackRequest,
    RegisterFinishRequest,
    RegisterStartRequest,
    SessionResponse,
    UserResponse,
    WalletRecoveryStartRequest,
    WalletRecoveryFinishRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Passkey / WebAuthn
# ---------------------------------------------------------------------------


@router.post("/register/start")
async def register_start(
    body: RegisterStartRequest,
    conn=Depends(get_db_conn),
):
    """Generate WebAuthn registration options and store challenge in DB."""
    from api.auth import passkey

    username = body.username or body.email or "user"
    result = await run_in_threadpool(passkey.start_registration, username, conn)
    return result


@router.post("/register/finish", response_model=SessionResponse)
@limiter.limit("10/minute")
async def register_finish(
    request: Request,
    body: RegisterFinishRequest,
    response: Response,
    conn=Depends(get_db_conn),
):
    """Verify registration credential, create user + passkey, set session cookie."""
    from api.auth import passkey as passkey_mod
    from api.auth.session import create_session

    try:
        user_id = await run_in_threadpool(
            passkey_mod.finish_registration,
            body.challenge_id,
            body.credential,
            conn,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {exc}",
        )

    # Load user info
    from api.auth._user_helpers import load_user_by_id, get_session_expires_at
    user_row = await run_in_threadpool(load_user_by_id, user_id, conn)
    await run_in_threadpool(create_session, user_id, response, conn)
    expires_at = get_session_expires_at()

    return SessionResponse(
        user=UserResponse(
            user_id=user_row["user_id"],
            near_account_id=user_row.get("near_account_id"),
            username=user_row.get("username"),
            email=user_row.get("email"),
            codename=user_row.get("codename"),
            is_admin=bool(user_row.get("is_admin", False)),
        ),
        expires_at=expires_at,
    )


@router.post("/login/start")
async def login_start(
    body: LoginStartRequest,
    conn=Depends(get_db_conn),
):
    """Generate WebAuthn authentication options and store challenge in DB."""
    from api.auth import passkey

    result = await run_in_threadpool(passkey.start_authentication, conn)
    return result


@router.post("/login/finish", response_model=SessionResponse)
@limiter.limit("10/minute")
async def login_finish(
    request: Request,
    body: LoginFinishRequest,
    response: Response,
    conn=Depends(get_db_conn),
):
    """Verify passkey assertion, update counter, create session."""
    from api.auth import passkey as passkey_mod
    from api.auth.session import create_session

    try:
        user_id = await run_in_threadpool(
            passkey_mod.finish_authentication,
            body.challenge_id,
            body.credential,
            conn,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {exc}",
        )

    from api.auth._user_helpers import load_user_by_id, get_session_expires_at
    user_row = await run_in_threadpool(load_user_by_id, user_id, conn)
    await run_in_threadpool(create_session, user_id, response, conn)
    expires_at = get_session_expires_at()

    return SessionResponse(
        user=UserResponse(
            user_id=user_row["user_id"],
            near_account_id=user_row.get("near_account_id"),
            username=user_row.get("username"),
            email=user_row.get("email"),
            codename=user_row.get("codename"),
            is_admin=bool(user_row.get("is_admin", False)),
        ),
        expires_at=expires_at,
    )


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


@router.get("/session", response_model=SessionResponse)
@limiter.limit("20/minute")
async def get_session(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Return the current session's user context (validates session cookie)."""
    from api.auth._user_helpers import get_session_expires_at

    return SessionResponse(
        user=UserResponse(
            user_id=user["user_id"],
            near_account_id=user.get("near_account_id"),
            username=user.get("username"),
            email=user.get("email"),
            codename=user.get("codename"),
            is_admin=bool(user.get("is_admin", False)),
        ),
        expires_at=get_session_expires_at(),
    )


@router.post("/logout")
async def logout(
    response: Response,
    neartax_session: Optional[str] = Cookie(default=None),
    conn=Depends(get_db_conn),
):
    """Destroy the current session cookie and remove it from the DB."""
    from api.auth.session import destroy_session

    if neartax_session:
        await run_in_threadpool(destroy_session, neartax_session, response, conn)
    else:
        response.delete_cookie(key="neartax_session")

    return {"logged_out": True}


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------


@router.get("/oauth/start")
@limiter.limit("20/minute")
async def oauth_start(
    request: Request,
    conn=Depends(get_db_conn),
):
    """Generate Google OAuth redirect URL with PKCE state stored in DB."""
    from api.auth.oauth import start_google_oauth

    result = await run_in_threadpool(start_google_oauth, conn)
    return result


@router.post("/oauth/callback", response_model=SessionResponse)
@limiter.limit("20/minute")
async def oauth_callback(
    request: Request,
    body: OAuthCallbackRequest,
    response: Response,
    conn=Depends(get_db_conn),
):
    """Exchange OAuth code for token, upsert user by email, create session."""
    from api.auth.oauth import finish_google_oauth
    from api.auth.session import create_session
    from api.auth._user_helpers import load_user_by_id, get_session_expires_at

    try:
        user_id = await run_in_threadpool(finish_google_oauth, body.code, body.state, conn)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth failed: {exc}",
        )

    user_row = await run_in_threadpool(load_user_by_id, user_id, conn)
    await run_in_threadpool(create_session, user_id, response, conn)
    expires_at = get_session_expires_at()

    return SessionResponse(
        user=UserResponse(
            user_id=user_row["user_id"],
            near_account_id=user_row.get("near_account_id"),
            username=user_row.get("username"),
            email=user_row.get("email"),
            codename=user_row.get("codename"),
            is_admin=bool(user_row.get("is_admin", False)),
        ),
        expires_at=expires_at,
    )


# ---------------------------------------------------------------------------
# Email magic link
# ---------------------------------------------------------------------------


@router.post("/magic-link/request")
@limiter.limit("10/minute")
async def magic_link_request(
    request: Request,
    body: MagicLinkRequest,
    conn=Depends(get_db_conn),
):
    """Send a magic link email; stores token in magic_link_tokens."""
    from api.auth.magic_link import request_magic_link

    await run_in_threadpool(request_magic_link, body.email, conn)
    return {"sent": True}


@router.get("/magic-link/verify", response_model=SessionResponse)
@limiter.limit("10/minute")
async def magic_link_verify(
    request: Request,
    token: str,
    response: Response,
    conn=Depends(get_db_conn),
):
    """Verify magic link token, create session, return session response."""
    from api.auth.magic_link import verify_magic_link
    from api.auth.session import create_session
    from api.auth._user_helpers import load_user_by_id, get_session_expires_at

    try:
        user_id = await run_in_threadpool(verify_magic_link, token, conn)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {exc}",
        )

    user_row = await run_in_threadpool(load_user_by_id, user_id, conn)
    await run_in_threadpool(create_session, user_id, response, conn)
    expires_at = get_session_expires_at()

    return SessionResponse(
        user=UserResponse(
            user_id=user_row["user_id"],
            near_account_id=user_row.get("near_account_id"),
            username=user_row.get("username"),
            email=user_row.get("email"),
            codename=user_row.get("codename"),
            is_admin=bool(user_row.get("is_admin", False)),
        ),
        expires_at=expires_at,
    )


# ---------------------------------------------------------------------------
# Account recovery
# ---------------------------------------------------------------------------


@router.post("/recovery/wallet/start")
@limiter.limit("10/minute")
async def wallet_recovery_start(
    request: Request,
    conn=Depends(get_db_conn),
):
    """Generate a challenge for wallet-based account recovery."""
    import secrets
    from datetime import datetime, timezone, timedelta

    challenge = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO challenges (id, challenge, challenge_type, expires_at)
            VALUES (%s, %s, 'authentication', %s)
            """,
            (challenge, challenge.encode(), expires_at),
        )
    finally:
        cur.close()
    conn.commit()

    return {"challenge": challenge, "expires_at": expires_at.isoformat()}


@router.post("/recovery/wallet/finish", response_model=SessionResponse)
@limiter.limit("10/minute")
async def wallet_recovery_finish(
    request: Request,
    body: WalletRecoveryFinishRequest,
    response: Response,
    conn=Depends(get_db_conn),
):
    """Verify wallet signature and recover account by creating a new session."""
    from api.auth.session import create_session
    from api.auth._user_helpers import load_user_by_id, get_session_expires_at

    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM users WHERE near_account_id = %s",
            (body.near_account_id,),
        )
        row = cur.fetchone()
    finally:
        cur.close()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No account found for {body.near_account_id}",
        )

    user_id = row[0]

    # Verify the challenge exists and hasn't expired
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM challenges WHERE id = %s AND expires_at > NOW()",
            (body.challenge,),
        )
        challenge_row = cur.fetchone()
        if challenge_row:
            cur.execute("DELETE FROM challenges WHERE id = %s", (body.challenge,))
    finally:
        cur.close()
    conn.commit()

    if challenge_row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Challenge expired or invalid",
        )

    user_row = await run_in_threadpool(load_user_by_id, user_id, conn)
    await run_in_threadpool(create_session, user_id, response, conn)
    expires_at = get_session_expires_at()

    return SessionResponse(
        user=UserResponse(
            user_id=user_row["user_id"],
            near_account_id=user_row.get("near_account_id"),
            username=user_row.get("username"),
            email=user_row.get("email"),
            codename=user_row.get("codename"),
            is_admin=bool(user_row.get("is_admin", False)),
        ),
        expires_at=expires_at,
    )


@router.post("/recovery/email")
@limiter.limit("10/minute")
async def email_recovery(
    request: Request,
    body: MagicLinkRequest,
    conn=Depends(get_db_conn),
):
    """Send a recovery magic link to the user's registered email."""
    from api.auth.magic_link import request_magic_link

    await run_in_threadpool(request_magic_link, body.email, conn)
    return {"sent": True}
