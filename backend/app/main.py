import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import api_router
from app.core.config import get_settings

logger = logging.getLogger("app")


def error_body(code: str, message: str, details: object | None = None) -> dict:
    """Every error response has the same shape: {"error": {"code", "message", "details"?}}."""
    body: dict = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_production()

    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
    )

    # Development: allow the Expo web dev server from this machine or the local network.
    # Production: only the origins listed in CORS_ORIGINS.
    dev_origins = None
    if settings.environment != "production":
        dev_origins = r"https?://(localhost|127\.0\.0\.1|10(\.\d{1,3}){3}|192\.168(\.\d{1,3}){2}|172\.(1[6-9]|2\d|3[01])(\.\d{1,3}){2})(:\d+)?"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=dev_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
        allow_credentials=False,  # bearer tokens, no cookies
        max_age=600,
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        code = detail.get("code", "http_error")
        message = detail.get("message", "") if detail else str(exc.detail)
        body = error_body(code, message)
        # Extra, deliberately-set fields (e.g. auth_url for incremental consent) travel with the error.
        body["error"].update({k: v for k, v in detail.items() if k not in ("code", "message")})
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # Strip submitted values from the echo so passwords/codes are never reflected or logged.
        details = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(error_body("validation_error", "Invalid request", details), status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(error_body("internal_error", "Something went wrong"), status_code=500)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "environment": settings.environment}

    app.include_router(api_router)
    return app


app = create_app()
