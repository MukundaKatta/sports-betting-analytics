"""Base API client with rate limiting and retries."""

from __future__ import annotations

import httpx
import time
import logging

from sba.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class BaseAPIClient:
    BASE_URL: str = ""

    def __init__(self, api_key: str = "", rate_limit: int = 30, period: float = 60.0):
        self.api_key = api_key
        self.rate_limiter = RateLimiter(rate_limit, period)
        self._remaining_credits: int | None = None

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
                if e.response.status_code == 429:
                    wait = 2 ** attempt * 5
                    logger.warning(f"Rate limited, waiting {wait}s")
                    time.sleep(wait)
                    last_exc = e
                    continue
                raise
            except httpx.RequestError as e:
                last_exc = e
                if attempt == 2:
                    raise
                logger.warning(f"Request error (attempt {attempt + 1}/3): {e}")
                time.sleep(2 ** attempt)
        raise RuntimeError(f"All retry attempts failed for {endpoint}") from last_exc

    def _get_headers(self) -> dict:
        return {}

    def _track_credits(self, headers: dict):
        remaining = headers.get("x-requests-remaining")
        if remaining is not None:
            self._remaining_credits = int(remaining)

    @property
    def remaining_credits(self) -> int | None:
        return self._remaining_credits
