import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

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

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = exc.detail.get("code", "http_error") if isinstance(exc.detail, dict) else "http_error"
        message = exc.detail.get("message", "") if isinstance(exc.detail, dict) else str(exc.detail)
        return JSONResponse(error_body(code, message), status_code=exc.status_code, headers=exc.headers)

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

    return app


app = create_app()
