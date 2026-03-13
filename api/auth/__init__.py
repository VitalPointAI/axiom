"""Auth sub-package — WebAuthn, magic link, and OAuth handlers.

Modules:
  session.py      — create_session / destroy_session (HTTP-only cookie + sessions table)
  passkey.py      — WebAuthn register/login via the webauthn library
  oauth.py        — Google OAuth PKCE flow
  magic_link.py   — Email magic link generation and verification
  router.py       — All /auth/* FastAPI endpoints

The router is registered in api/main.py via:
  application.include_router(auth_router)
"""

from api.auth.router import router

__all__ = ["router"]
