"""FastAPI web application for Sports Betting Analytics."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sba import __version__
from sba.config import get_settings
from sba.config.logging import setup_logging
from sba.data.db import init_db
from sba.web.api import router as api_router
from sba.web.errors import APIError, api_error_response
from sba.web.middleware import (
    APIKeyMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from sba.web.sse import router as sse_router
from sba.web.views import router as views_router

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


_ALLOWED_PERSISTED_SETTINGS = {
    "SBA_DEFAULT_SPORT", "SBA_DEFAULT_REGION", "SBA_EV_THRESHOLD",
    "SBA_KELLY_FRACTION", "SBA_BANKROLL", "SBA_REFRESH_INTERVAL_SECONDS",
    "SBA_LOG_LEVEL",
}


def _restore_persisted_settings():
    """Load settings saved to DB and apply to environment.

    Only allows known SBA_ setting keys to prevent environment injection.
    """
    import os

    try:
        from sba.data.db import get_connection
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT key, value FROM user_stats WHERE key LIKE 'setting_%'"
            ).fetchall()
        for row in rows:
            env_key = row["key"].replace("setting_", "", 1)
            if env_key not in _ALLOWED_PERSISTED_SETTINGS:
                logger.warning("Blocked persisted setting %s (not in allowlist)", env_key)
                continue
            os.environ[env_key] = str(row["value"])
            logger.debug("Restored setting %s from DB", env_key)
    except Exception:
        logger.debug("No persisted settings to restore")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _settings = get_settings()
    log_fmt = "json" if _settings.LOG_LEVEL == "WARNING" else "text"
    setup_logging(level=_settings.LOG_LEVEL, fmt=log_fmt)
    init_db()
    _restore_persisted_settings()
    logger.info("SBA Web Dashboard started (v%s)", app.version)
    yield
    logger.info("SBA Web Dashboard stopped")


app = FastAPI(
    title="SBA — Sports Betting Analytics",
    description="Professional sports betting analytics platform with ML-powered predictions",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ── Middleware stack (executed bottom-to-top) ────────────────────────

# GZip compression for API responses (min 500 bytes to avoid overhead on small responses)
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS — loaded from settings so it works in production deployments
settings = get_settings()
cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID"],
    allow_credentials=True,
)

# Rate limiting — single configurable middleware (removed duplicate inline limiter)
app.add_middleware(
    RateLimitMiddleware,
    max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
)

# Security headers (CSP, X-Frame-Options, etc.)
app.add_middleware(SecurityHeadersMiddleware)

# Request ID for tracing
app.add_middleware(RequestIDMiddleware)

# API key authentication (opt-in via SBA_API_KEY env var)
if settings.API_KEY:
    app.add_middleware(APIKeyMiddleware, api_key=settings.API_KEY)


# Request timing middleware
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Response-Time"] = f"{elapsed:.3f}s"
    return response


# Structured API error handler
@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    return api_error_response(exc)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        "Unhandled error on %s %s [%s]: %s",
        request.method, request.url.path, request_id, exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": request_id},
    )


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(str(STATIC_DIR / "sw.js"), media_type="application/javascript")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api_router, prefix="/api")
app.include_router(sse_router, prefix="/api")
app.include_router(views_router)


def create_app() -> FastAPI:
    return app
