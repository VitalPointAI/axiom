"""Pydantic schemas package for request/response validation."""

from api.schemas.auth import (
    LoginFinishRequest,
    LoginStartRequest,
    MagicLinkRequest,
    OAuthCallbackRequest,
    RegisterFinishRequest,
    RegisterStartRequest,
    SessionResponse,
    UserResponse,
)
from api.schemas.common import ErrorResponse, JobStatusResponse, PaginatedResponse

__all__ = [
    "ErrorResponse",
    "PaginatedResponse",
    "JobStatusResponse",
    "RegisterStartRequest",
    "RegisterFinishRequest",
    "LoginStartRequest",
    "LoginFinishRequest",
    "MagicLinkRequest",
    "OAuthCallbackRequest",
    "SessionResponse",
    "UserResponse",
]
