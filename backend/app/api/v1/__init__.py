from fastapi import APIRouter

from app.api.v1 import auth, billing, hydration, me, medications

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(hydration.router)
api_router.include_router(billing.router)
api_router.include_router(medications.router)
