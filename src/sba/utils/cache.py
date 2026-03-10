"""Thread-safe TTL cache with bounded memory and decorator support.

v2.4: Added threading lock, max entries with LRU eviction, stale cleanup.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from functools import wraps
from typing import Any

_MAX_ENTRIES = 1000


class TTLCache:
    """Thread-safe TTL cache with bounded size for API response data."""

    def __init__(self, max_entries: int = _MAX_ENTRIES):
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._max_entries = max_entries

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key in self._store:
                value, expires = self._store[key]
                if time.monotonic() < expires:
                    self._hits += 1
                    return value
                del self._store[key]
            self._misses += 1
            return None

    def set(self, key: str, value: Any, ttl: float = 60.0):
        with self._lock:
            if len(self._store) >= self._max_entries:
                self._evict_expired()
            if len(self._store) >= self._max_entries:
                self._evict_oldest(len(self._store) - self._max_entries + 1)
            self._store[key] = (value, time.monotonic() + ttl)

    def invalidate(self, prefix: str = ""):
        with self._lock:
            if not prefix:
                self._store.clear()
            else:
                keys = [k for k in self._store if k.startswith(prefix)]
                for k in keys:
                    del self._store[k]

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if exp <= now]
        for k in expired:
            del self._store[k]

    def _evict_oldest(self, count: int) -> None:
        if count <= 0:
            return
        sorted_keys = sorted(self._store, key=lambda k: self._store[k][1])
        for k in sorted_keys[:count]:
            del self._store[k]

    @property
    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._store),
                "max_entries": self._max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / max(total, 1) * 100, 1),
            }


cache = TTLCache()


def cached_response(ttl: float = 30.0, prefix: str = ""):
    """Decorator to cache endpoint responses for a given TTL.

    Usage:
        @router.get("/sports")
        @cached_response(ttl=300, prefix="sports")
        def get_sports():
            ...
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key from function name + args
            key_parts = [prefix or func.__name__]
            if args:
                key_parts.append(str(args))
            if kwargs:
                sorted_kwargs = sorted(kwargs.items())
                key_parts.append(
                    hashlib.md5(json.dumps(sorted_kwargs, default=str).encode()).hexdigest()[:12]
                )
            cache_key = ":".join(key_parts)

            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl=ttl)
            return result

        return wrapper

    return decorator
