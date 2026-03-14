"""Shared slowapi rate limiter instance.

Import this module to access the limiter singleton:

    from api.rate_limit import limiter

Register it on the FastAPI app in api/main.py:

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Single shared limiter — keyed by client IP address.
# Backends default to in-memory; swap to Redis via storage_uri for multi-process deployments.
limiter = Limiter(key_func=get_remote_address)
