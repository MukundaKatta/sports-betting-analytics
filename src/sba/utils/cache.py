"""Simple TTL cache for API responses."""
from __future__ import annotations

import time
from typing import Any


class TTLCache:
    """Thread-safe TTL cache for API response data."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        if key in self._store:
            value, expires = self._store[key]
            if time.monotonic() < expires:
                return value
            del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl: float = 60.0):
        self._store[key] = (value, time.monotonic() + ttl)

    def invalidate(self, prefix: str = ""):
        if not prefix:
            self._store.clear()
        else:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]


cache = TTLCache()
