"""Base API client with rate limiting, retries, and async support."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from sba.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class BaseAPIClient:
    BASE_URL: str = ""

    def __init__(self, api_key: str = "", rate_limit: int = 30, period: float = 60.0):
        self.api_key = api_key
        self.rate_limiter = RateLimiter(rate_limit, period)
        self._remaining_credits: int | None = None
        self._async_client: httpx.AsyncClient | None = None

    # ── Synchronous fetch (CLI usage) ─────────────────────────────────

    def fetch(self, endpoint: str, params: dict | None = None) -> dict | list:
        self.rate_limiter.acquire_sync()
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers()

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(url, params=params, headers=headers)
                    self._track_credits(resp.headers)
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 429 or 500 <= status < 600:
                    wait = 2 ** attempt * 5
                    logger.warning(f"HTTP {status} on {url}, waiting {wait}s (attempt {attempt + 1}/3)")
                    time.sleep(wait)
                    last_exc = e
                    continue
                logger.error(f"HTTP {status} on {url}: {e.response.text[:500]}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request error on {url}: {e}")
                last_exc = e
                if attempt == 2:
                    raise
                logger.warning(f"Request error (attempt {attempt + 1}/3): {e}")
                time.sleep(2 ** attempt)
        raise RuntimeError(f"All retry attempts failed for {endpoint}") from last_exc

    # ── Async fetch (web endpoint usage) ──────────────────────────────

    async def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(timeout=30.0)
        return self._async_client

    async def async_fetch(self, endpoint: str, params: dict | None = None) -> dict | list:
        """Async version of fetch() for use in FastAPI endpoints."""
        await self.rate_limiter.acquire()
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers()
        client = await self._get_async_client()

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = await client.get(url, params=params, headers=headers)
                self._track_credits(dict(resp.headers))
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 429 or 500 <= status < 600:
                    wait = 2 ** attempt * 5
                    logger.warning(f"HTTP {status} on {url}, waiting {wait}s (attempt {attempt + 1}/3)")
                    await asyncio.sleep(wait)
                    last_exc = e
                    continue
                logger.error(f"HTTP {status} on {url}: {e.response.text[:500]}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request error on {url}: {e}")
                last_exc = e
                if attempt == 2:
                    raise
                logger.warning(f"Request error (attempt {attempt + 1}/3): {e}")
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"All retry attempts failed for {endpoint}") from last_exc

    async def aclose(self) -> None:
        """Close the async HTTP client. Call during app shutdown."""
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()
            self._async_client = None

    # ── Shared helpers ────────────────────────────────────────────────

    def _get_headers(self) -> dict:
        return {}

    def _track_credits(self, headers: dict):
        remaining = headers.get("x-requests-remaining")
        if remaining is not None:
            self._remaining_credits = int(remaining)

    @property
    def remaining_credits(self) -> int | None:
        return self._remaining_credits
