from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.api.admin_deps import Permission
from app.api.deps import DB
from app.services import admin_stats

router = APIRouter(prefix="/overview", tags=["admin: overview"])


@router.get("")
def get_overview(
    ctx: Permission("dashboard.read"),
    db: DB,
    from_: date | None = Query(default=None, alias="from", description="Inclusive UTC date; default 29 days before `to`"),
    to: date | None = Query(default=None, description="Inclusive UTC date; default today"),
):
    """KPIs, chart series, feature usage and recent activity, all aggregated from live data.
    Revenue (and payment items in recent activity) need `payments.read`; admin actions need `audit.read`."""
    try:
        r = admin_stats.parse_range(from_, to)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"code": "invalid_range", "message": str(exc)}) from None
    return admin_stats.overview(db, r, can_payments=ctx.can("payments.read"), can_audit=ctx.can("audit.read"))
