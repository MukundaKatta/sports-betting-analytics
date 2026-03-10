"""Enhanced notification/alert system API endpoints."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sba.data.db import get_connection

logger = logging.getLogger(__name__)
router = APIRouter(tags=["notifications"])


class NotificationRuleRequest(BaseModel):
    name: str
    rule_type: str  # "ev_threshold", "arb_alert", "line_move", "clv_alert"
    sport: str = ""
    min_ev: float = 0
    min_odds: int = -1000
    max_odds: int = 1000
    bookmakers: str = ""  # Comma-separated list
    webhook_url: str = ""
    enabled: bool = True


@router.get("/notification-rules")
def get_notification_rules():
    """Get all notification rules."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM notification_rules ORDER BY created_at DESC"
        ).fetchall()

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "rule_type": r["rule_type"],
            "sport": r["sport"],
            "min_ev": r["min_ev"],
            "min_odds": r["min_odds"],
            "max_odds": r["max_odds"],
            "bookmakers": r["bookmakers"],
            "webhook_url": r["webhook_url"],
            "enabled": bool(r["enabled"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.post("/notification-rules")
def create_notification_rule(req: NotificationRuleRequest):
    """Create a new notification rule."""
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO notification_rules
               (name, rule_type, sport, min_ev, min_odds, max_odds, bookmakers, webhook_url, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (req.name, req.rule_type, req.sport, req.min_ev,
             req.min_odds, req.max_odds, req.bookmakers,
             req.webhook_url, int(req.enabled)),
        )
    return {"id": cursor.lastrowid, "name": req.name, "status": "created"}


@router.put("/notification-rules/{rule_id}")
def update_notification_rule(rule_id: int, req: NotificationRuleRequest):
    """Update a notification rule."""
    with get_connection() as conn:
        conn.execute(
            """UPDATE notification_rules SET
               name=?, rule_type=?, sport=?, min_ev=?, min_odds=?, max_odds=?,
               bookmakers=?, webhook_url=?, enabled=?
               WHERE id=?""",
            (req.name, req.rule_type, req.sport, req.min_ev,
             req.min_odds, req.max_odds, req.bookmakers,
             req.webhook_url, int(req.enabled), rule_id),
        )
    return {"id": rule_id, "status": "updated"}


@router.delete("/notification-rules/{rule_id}")
def delete_notification_rule(rule_id: int):
    """Delete a notification rule."""
    with get_connection() as conn:
        conn.execute("DELETE FROM notification_rules WHERE id = ?", (rule_id,))
    return {"id": rule_id, "status": "deleted"}


@router.post("/notification-rules/{rule_id}/toggle")
def toggle_notification_rule(rule_id: int):
    """Toggle a notification rule on/off."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE notification_rules SET enabled = NOT enabled WHERE id = ?",
            (rule_id,),
        )
        row = conn.execute(
            "SELECT enabled FROM notification_rules WHERE id = ?", (rule_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Rule not found")
    return {"id": rule_id, "enabled": bool(row["enabled"])}


@router.post("/notifications/test-webhook")
def test_webhook(webhook_url: str = ""):
    """Test a webhook URL by sending a sample notification."""
    if not webhook_url:
        return {"error": "webhook_url is required"}

    import httpx

    payload = {
        "text": "[SBA Test] Sports Betting Analytics webhook test successful!",
        "event": "test",
        "data": {
            "message": "If you see this, your webhook is working correctly.",
            "source": "SBA — Sports Betting Analytics",
        },
    }

    try:
        resp = httpx.post(webhook_url, json=payload, timeout=10)
        return {
            "status": "sent",
            "response_code": resp.status_code,
            "webhook_url": webhook_url,
        }
    except (httpx.HTTPError, ConnectionError, TimeoutError) as exc:
        logger.warning(f"Webhook test failed for {webhook_url}: {exc}")
        return {"status": "failed", "error": str(exc)}
