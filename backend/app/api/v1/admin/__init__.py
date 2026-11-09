"""Owner/admin dashboard API, mounted at /api/v1/admin. Every route is permission-checked server-side."""

from fastapi import APIRouter

from app.api.v1.admin import auth, overview, roles

admin_router = APIRouter(prefix="/admin")
admin_router.include_router(auth.router)
admin_router.include_router(roles.router)
admin_router.include_router(overview.router)
