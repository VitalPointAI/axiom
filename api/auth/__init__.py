"""Auth sub-package — WebAuthn, magic link, and OAuth handlers.

Routers are registered in later plans (07-02: WebAuthn, 07-03: magic link/OAuth).
This package provides the auth router stub used by api/main.py.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])
