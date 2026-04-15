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
from api.routers.assets import router as assets_router  # noqa: F401
from api.routers.admin import router as admin_router  # noqa: F401 — Plan 13-05
from api.routers.streaming import router as streaming_router  # noqa: F401 — Plan 13-05
from api.routers.staking import router as staking_router  # noqa: F401
from api.routers.waitlist import router as waitlist_router  # noqa: F401 — Plan 14-02
from api.routers.settings import router as settings_router  # noqa: F401 — Plan 16-07
from api.routers.internal_pipeline import router as internal_pipeline_router  # noqa: F401 — Plan 16-07
