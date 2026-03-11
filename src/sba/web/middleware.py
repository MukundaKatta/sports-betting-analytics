"""Middleware for the SBA web application.

Production-grade middleware stack:
- Rate limiting with memory bounds and X-Forwarded-For support
- Request ID tracking for distributed tracing
- API key validation for external data endpoints
"""

from __future__ import annotations

import hmac
import time
import uuid
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP-based rate limiter with memory bounds and proxy support.

    Improvements over v2.2:
    - Respects X-Forwarded-For for clients behind proxies/load balancers
    - Bounded memory: evicts IPs not seen in 2x window to prevent unbounded growth
    - Configurable from settings
    """

    def __init__(self, app, max_requests: int = 120, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = window_seconds * 2

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, respecting X-Forwarded-For behind proxies."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # First IP in the chain is the original client
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup_stale_entries(self, now: float) -> None:
        """Periodically evict stale IPs to bound memory usage."""
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        stale_cutoff = now - self._cleanup_interval
        stale_keys = [
            ip for ip, hits in self._hits.items()
            if not hits or hits[-1] < stale_cutoff
        ]
        for key in stale_keys:
            del self._hits[key]

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and static assets
        path = request.url.path
        if path in ("/api/health", "/sw.js") or path.startswith("/static"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.monotonic()

        # Periodic cleanup of stale entries
        self._cleanup_stale_entries(now)

        # Prune old entries for this IP
        self._hits[client_ip] = [
            t for t in self._hits[client_ip] if now - t < self.window
        ]

        if len(self._hits[client_ip]) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests. Please slow down."},
                headers={"Retry-After": str(self.window)},
            )

        self._hits[client_ip].append(now)
        return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Adds a unique request ID to every response for tracing and debugging.

    The ID is available in the response header X-Request-ID and can be used
    to correlate logs, errors, and support tickets.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())[:12]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Optional API key authentication for /api/* endpoints.

    When API_KEY is configured, all API requests must include either:
    - Header: X-API-Key: <key>
    - Query parameter: ?api_key=<key>

    Unauthenticated paths: health, docs, redoc, openapi.json, static, views.
    When API_KEY is empty (default), all requests pass through (dev mode).
    """

    # Paths that never require authentication
    PUBLIC_PATHS = {"/api/health", "/api/docs", "/api/redoc", "/api/openapi.json"}

    def __init__(self, app, api_key: str = ""):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        # Skip if no key configured (development mode)
        if not self.api_key:
            return await call_next(request)

        path = request.url.path

        # Only protect /api/* paths (not views, static, etc.)
        if not path.startswith("/api/"):
            return await call_next(request)

        # Allow public API paths
        if path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Check for API key in header or query param
        provided_key = (
            request.headers.get("x-api-key")
            or request.query_params.get("api_key")
        )

        if not provided_key or not hmac.compare_digest(provided_key, self.api_key):
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid or missing API key"},
                headers={"WWW-Authenticate": "ApiKey"},
            )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to all responses.

    - X-Content-Type-Options: prevents MIME sniffing
    - X-Frame-Options: prevents clickjacking
    - Referrer-Policy: limits referrer information leakage
    - Permissions-Policy: restricts browser features
    - Content-Security-Policy: restricts resource loading sources
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        # CSP: allow self, inline styles/scripts (needed for Jinja templates),
        # Google Fonts, and data: URIs for SVG favicon
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        return response
