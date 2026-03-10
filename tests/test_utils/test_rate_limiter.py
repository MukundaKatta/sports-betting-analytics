"""Tests for rate limiter."""

import time

import pytest

from sba.utils.rate_limiter import RateLimiter


class TestRateLimiterSync:
    def test_allows_within_limit(self):
        limiter = RateLimiter(max_calls=5, period=60.0)
        for _ in range(5):
            limiter.acquire_sync()
        # Should have 5 calls recorded
        assert len(limiter.calls) == 5

    def test_cleans_expired_calls(self):
        limiter = RateLimiter(max_calls=2, period=0.1)
        limiter.acquire_sync()
        time.sleep(0.15)
        limiter.acquire_sync()
        # Old call should be expired
        assert len(limiter.calls) == 1

    def test_blocks_over_limit(self):
        limiter = RateLimiter(max_calls=2, period=0.5)
        limiter.acquire_sync()
        limiter.acquire_sync()
        start = time.monotonic()
        limiter.acquire_sync()
        elapsed = time.monotonic() - start
        # Should have waited for the period to expire
        assert elapsed >= 0.3


class TestRateLimiterAsync:
    @pytest.mark.asyncio
    async def test_async_acquire(self):
        limiter = RateLimiter(max_calls=3, period=60.0)
        await limiter.acquire()
        await limiter.acquire()
        assert len(limiter.calls) == 2
