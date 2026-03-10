"""FastAPI web application for Sports Betting Analytics."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sba import __version__
from sba.config import get_settings
from sba.config.logging import setup_logging
from sba.data.db import init_db
from sba.web.api import router as api_router
from sba.web.errors import APIError, api_error_response
from sba.web.middleware import APIKeyMiddleware, RateLimitMiddleware, RequestIDMiddleware
from sba.web.sse import router as sse_router
from sba.web.views import router as views_router

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


def _restore_persisted_settings():
    """Load settings saved to DB and apply to environment."""
    try:
        from sba.data.db import get_connection
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT key, value FROM user_stats WHERE key LIKE 'setting_%'"
            ).fetchall()
        for row in rows:
            env_key = row["key"].replace("setting_", "", 1)
            os.environ[env_key] = row["value"]
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

# CORS — loaded from settings so it works in production deployments
settings = get_settings()
cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting — configurable from env
app.add_middleware(
    RateLimitMiddleware,
    max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
)

# Request ID for tracing
app.add_middleware(RequestIDMiddleware)

# API key authentication (opt-in via SBA_API_KEY env var)
if settings.API_KEY:
    app.add_middleware(APIKeyMiddleware, api_key=settings.API_KEY)


# Simple in-memory rate limiter — per-IP, configurable via SBA_RATE_LIMIT
# Set SBA_RATE_LIMIT=0 to disable (e.g. in tests)
_rate_limit = int(os.getenv("SBA_RATE_LIMIT", "120"))  # requests per minute
_rate_window = 60  # seconds
_rate_store: dict[str, list[float]] = {}


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limit API endpoints per client IP."""
    if _rate_limit > 0 and request.url.path.startswith("/api/"):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        # Clean old entries
        hits = _rate_store.get(client_ip, [])
        hits = [t for t in hits if now - t < _rate_window]
        if len(hits) >= _rate_limit:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": _rate_window},
                headers={"Retry-After": str(_rate_window)},
            )
        hits.append(now)
        _rate_store[client_ip] = hits

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
