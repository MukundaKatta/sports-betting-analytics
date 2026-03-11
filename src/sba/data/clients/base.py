"""Base API client with rate limiting, retries, and async support."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from sba.config.constants import (
    HTTP_TIMEOUT_SECONDS,
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_MULTIPLIER,
    RETRY_BASE_DELAY,
    RETRYABLE_STATUS_CODES,
)
from sba.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


def _is_retryable(status_code: int) -> bool:
    """Check if an HTTP status code should be retried."""
    return status_code in RETRYABLE_STATUS_CODES


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
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
                    resp = client.get(url, params=params, headers=headers)
                    self._track_credits(resp.headers)
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if _is_retryable(status):
                    wait = RETRY_BACKOFF_MULTIPLIER ** attempt * RETRY_BASE_DELAY
                    logger.warning(
                        "HTTP %d on %s, waiting %ds (attempt %d/%d)",
                        status, url, wait, attempt + 1, MAX_RETRY_ATTEMPTS,
                    )
                    time.sleep(wait)
                    last_exc = e
                    continue
                logger.error("HTTP %d on %s: %s", status, url, e.response.text[:500])
                raise
            except httpx.RequestError as e:
                logger.error("Request error on %s: %s", url, e)
                last_exc = e
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    raise
                wait = RETRY_BACKOFF_MULTIPLIER ** attempt
                logger.warning(
                    "Request error (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1, MAX_RETRY_ATTEMPTS, wait, e,
                )
                time.sleep(wait)
        raise RuntimeError(f"All retry attempts failed for {endpoint}") from last_exc

    # ── Async fetch (web endpoint usage) ──────────────────────────────

    async def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)
        return self._async_client

    async def async_fetch(self, endpoint: str, params: dict | None = None) -> dict | list:
        """Async version of fetch() for use in FastAPI endpoints."""
        await self.rate_limiter.acquire()
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers()
        client = await self._get_async_client()

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                resp = await client.get(url, params=params, headers=headers)
                self._track_credits(dict(resp.headers))
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if _is_retryable(status):
                    wait = RETRY_BACKOFF_MULTIPLIER ** attempt * RETRY_BASE_DELAY
                    logger.warning(
                        "HTTP %d on %s, waiting %ds (attempt %d/%d)",
                        status, url, wait, attempt + 1, MAX_RETRY_ATTEMPTS,
                    )
                    await asyncio.sleep(wait)
                    last_exc = e
                    continue
                logger.error("HTTP %d on %s: %s", status, url, e.response.text[:500])
                raise
            except httpx.RequestError as e:
                logger.error("Request error on %s: %s", url, e)
                last_exc = e
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    raise
                wait = RETRY_BACKOFF_MULTIPLIER ** attempt
                logger.warning(
                    "Request error (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1, MAX_RETRY_ATTEMPTS, wait, e,
                )
                await asyncio.sleep(wait)
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
