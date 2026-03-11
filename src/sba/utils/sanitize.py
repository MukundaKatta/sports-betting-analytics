"""Input sanitization utilities for security hardening.

Provides functions to clean and validate user inputs across the application.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from sba.config.constants import MAX_PAGE_SIZE, DEFAULT_PAGE_SIZE


def sanitize_string(value: str, max_length: int = 500) -> str:
    """Sanitize a string input by stripping whitespace and limiting length.

    Removes null bytes and control characters (except newlines/tabs).
    """
    if not value:
        return ""
    # Remove null bytes
    value = value.replace("\x00", "")
    # Remove control characters except \n and \t
    value = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    return value.strip()[:max_length]


def sanitize_webhook_url(url: str) -> str:
    """Validate and sanitize a webhook URL.

    Only allows http and https schemes. Rejects private/internal IPs.
    """
    if not url:
        return ""

    url = url.strip()
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid webhook URL scheme: {parsed.scheme}. Only http/https allowed.")

    if not parsed.hostname:
        raise ValueError("Webhook URL must have a valid hostname")

    # Block common internal/private hostnames
    blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "metadata.google.internal"}
    if parsed.hostname.lower() in blocked_hosts:
        raise ValueError(f"Webhook URL cannot point to internal host: {parsed.hostname}")

    # Block private IP ranges
    if _is_private_ip(parsed.hostname):
        raise ValueError(f"Webhook URL cannot point to private IP: {parsed.hostname}")

    return url


def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname looks like a private/reserved IP address."""
    private_patterns = [
        r"^10\.",
        r"^172\.(1[6-9]|2[0-9]|3[01])\.",
        r"^192\.168\.",
        r"^169\.254\.",
    ]
    return any(re.match(pat, hostname) for pat in private_patterns)


def sanitize_pagination(limit: int | None = None, offset: int | None = None) -> tuple[int, int]:
    """Sanitize and clamp pagination parameters.

    Returns (limit, offset) with safe defaults and bounds.
    """
    if limit is None or limit <= 0:
        limit = DEFAULT_PAGE_SIZE
    limit = min(limit, MAX_PAGE_SIZE)

    if offset is None or offset < 0:
        offset = 0

    return limit, offset


def sanitize_sort_field(field: str, allowed_fields: set[str],
                        default: str = "created_at") -> str:
    """Validate a sort field against an allowlist."""
    field = field.strip().lower()
    if field not in allowed_fields:
        return default
    return field


def sanitize_sort_order(order: str) -> str:
    """Validate sort order is ASC or DESC."""
    order = order.strip().upper()
    return order if order in ("ASC", "DESC") else "DESC"
