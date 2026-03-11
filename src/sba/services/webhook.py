"""Webhook delivery service with retry logic.

Handles reliable delivery of webhook notifications with
exponential backoff retries and delivery tracking.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import httpx

from sba.config.constants import (
    WEBHOOK_MAX_RETRIES,
    WEBHOOK_RETRY_DELAYS,
    WEBHOOK_TIMEOUT_SECONDS,
)
from sba.data.db import get_connection

logger = logging.getLogger(__name__)


def deliver_webhook(webhook_url: str, payload: dict,
                    rule_id: int | None = None) -> dict:
    """Deliver a webhook with retry logic.

    Attempts delivery up to WEBHOOK_MAX_RETRIES times with increasing delays.
    Records delivery status in the webhook_deliveries table.

    Returns:
        Dict with delivery status and details.
    """
    delivery_id = _record_delivery(rule_id, webhook_url, payload)
    last_error = ""
    response_code = None

    for attempt in range(WEBHOOK_MAX_RETRIES):
        try:
            resp = httpx.post(
                webhook_url,
                json=payload,
                timeout=WEBHOOK_TIMEOUT_SECONDS,
            )
            response_code = resp.status_code

            if 200 <= resp.status_code < 300:
                _update_delivery(delivery_id, "delivered", attempt + 1,
                                 response_code=response_code)
                return {
                    "status": "delivered",
                    "response_code": response_code,
                    "attempts": attempt + 1,
                    "delivery_id": delivery_id,
                }

            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning(
                "Webhook delivery attempt %d/%d failed: %s",
                attempt + 1, WEBHOOK_MAX_RETRIES, last_error,
            )

        except (httpx.HTTPError, ConnectionError, TimeoutError, OSError) as exc:
            last_error = str(exc)
            logger.warning(
                "Webhook delivery attempt %d/%d error: %s",
                attempt + 1, WEBHOOK_MAX_RETRIES, last_error,
            )

        # Wait before retry (except on last attempt)
        if attempt < WEBHOOK_MAX_RETRIES - 1:
            delay = WEBHOOK_RETRY_DELAYS[min(attempt, len(WEBHOOK_RETRY_DELAYS) - 1)]
            time.sleep(delay)

    # All retries exhausted
    _update_delivery(delivery_id, "failed", WEBHOOK_MAX_RETRIES,
                     last_error=last_error, response_code=response_code)
    return {
        "status": "failed",
        "error": last_error,
        "attempts": WEBHOOK_MAX_RETRIES,
        "delivery_id": delivery_id,
    }


def get_delivery_history(rule_id: int | None = None,
                         limit: int = 50) -> list[dict]:
    """Get webhook delivery history, optionally filtered by rule."""
    with get_connection() as conn:
        if rule_id:
            rows = conn.execute(
                """SELECT * FROM webhook_deliveries
                   WHERE rule_id = ? ORDER BY created_at DESC LIMIT ?""",
                (rule_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM webhook_deliveries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

    return [
        {
            "id": r["id"],
            "rule_id": r["rule_id"],
            "webhook_url": r["webhook_url"],
            "status": r["status"],
            "attempts": r["attempts"],
            "response_code": r["response_code"],
            "last_error": r["last_error"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def _record_delivery(rule_id: int | None, webhook_url: str,
                     payload: dict) -> int | None:
    """Record a new delivery attempt in the database."""
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO webhook_deliveries
                   (rule_id, webhook_url, payload, status, attempts)
                   VALUES (?, ?, ?, 'pending', 0)""",
                (rule_id, webhook_url, json.dumps(payload)),
            )
            return cursor.lastrowid
    except Exception:
        logger.debug("Could not record webhook delivery (table may not exist)")
        return None


def _update_delivery(delivery_id: int | None, status: str, attempts: int,
                     last_error: str = "", response_code: int | None = None) -> None:
    """Update a delivery record with the result."""
    if delivery_id is None:
        return
    try:
        with get_connection() as conn:
            conn.execute(
                """UPDATE webhook_deliveries SET
                   status = ?, attempts = ?, last_error = ?,
                   response_code = ?,
                   last_attempt_at = ?
                   WHERE id = ?""",
                (status, attempts, last_error, response_code,
                 datetime.now(timezone.utc).isoformat(), delivery_id),
            )
    except Exception:
        logger.debug("Could not update webhook delivery %s", delivery_id)
