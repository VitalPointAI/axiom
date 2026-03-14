"""Auth-related Pydantic schemas for WebAuthn, magic link, and OAuth flows."""

from typing import Any, Dict, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# WebAuthn / Passkey schemas
# ---------------------------------------------------------------------------


class RegisterStartRequest(BaseModel):
    """Start passkey registration — user provides their display name."""

    username: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None


class RegisterFinishRequest(BaseModel):
    """Complete passkey registration — client returns WebAuthn credential."""

    challenge_id: str
    credential: Dict[str, Any]  # Raw WebAuthn PublicKeyCredential JSON


class LoginStartRequest(BaseModel):
    """Start passkey authentication — optionally scoped to a specific user."""

    username: Optional[str] = None
    email: Optional[str] = None


class LoginFinishRequest(BaseModel):
    """Complete passkey authentication — client returns signed assertion."""

    challenge_id: str
    credential: Dict[str, Any]  # Raw WebAuthn PublicKeyCredential JSON


# ---------------------------------------------------------------------------
# Magic link schema
# ---------------------------------------------------------------------------


class MagicLinkRequest(BaseModel):
    """Request a magic link sent to the given email address."""

    email: str


# ---------------------------------------------------------------------------
# OAuth schema
# ---------------------------------------------------------------------------


class OAuthCallbackRequest(BaseModel):
    """OAuth callback parameters received from the identity provider."""

    code: str
    state: str
    provider: str = "google"


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """Public user profile returned on session check or after login."""

    user_id: int
    near_account_id: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    codename: Optional[str] = None
    is_admin: bool = False


class SessionResponse(BaseModel):
    """Successful auth response — session cookie is set HTTP-only by the server."""

    user: UserResponse
    expires_at: str  # ISO 8601 datetime string
