"""API data routers package.

Imports real router implementations as they are built. Stub routers remain
for endpoints not yet implemented, with auth-enforcing GET handlers.
"""

from fastapi import APIRouter, Depends  # noqa: F401 — re-exported for sub-routers

from api.dependencies import get_effective_user  # noqa: F401 — re-exported

# ---------------------------------------------------------------------------
# Real router implementations (added as each plan completes)
# ---------------------------------------------------------------------------

from api.routers.wallets import router as wallets_router  # noqa: F401 — Plan 07-03
from api.routers.portfolio import router as portfolio_router  # noqa: F401 — Plan 07-03
from api.routers.jobs import router as jobs_router  # noqa: F401 — Plan 07-03
from api.routers.transactions import router as transactions_router  # noqa: F401 — Plan 07-04
from api.routers.reports import router as reports_router  # noqa: F401 — Plan 07-05
from api.routers.reports import exchanges_router  # noqa: F401 — Plan 07-05
from api.routers.verification import router as verification_router  # noqa: F401 — Plan 07-05
from api.routers.audit import router as audit_router  # noqa: F401 — Plan 11-05
from api.routers.accountant import router as accountant_router  # noqa: F401
from api.routers.preferences import router as preferences_router  # noqa: F401 — Plan 12-01
