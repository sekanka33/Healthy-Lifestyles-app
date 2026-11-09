from fastapi import APIRouter

from app.api.v1.admin import admin_router
from app.api.v1 import auth, billing, calendar, fitness, hydration, me, medications, privacy, reports, weather

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(hydration.router)
api_router.include_router(billing.router)
api_router.include_router(medications.router)
api_router.include_router(fitness.router)
api_router.include_router(weather.router)
api_router.include_router(calendar.router)
api_router.include_router(reports.router)
api_router.include_router(privacy.router)
api_router.include_router(admin_router)
