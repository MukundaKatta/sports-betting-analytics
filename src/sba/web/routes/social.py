"""Community features (picks, leaderboard, alerts, watchlist) endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from sba.data.db import get_connection
from sba.utils.cache import cached_response
from sba.web.errors import safe_endpoint

logger = logging.getLogger(__name__)
router = APIRouter(tags=["social"])


# ── Pydantic models ─────────────────────────────────────────────────

class RegisterUserRequest(BaseModel):
    username: str  # max 50 chars enforced below
    display_name: str = ""

    def model_post_init(self, __context) -> None:
        if len(self.username) > 50 or len(self.username) < 1:
            raise ValueError("username must be 1-50 characters")
        if len(self.display_name) > 100:
            raise ValueError("display_name must be 100 characters or fewer")


class SubmitPickRequest(BaseModel):
    username: str
    event_id: str
    market: str
    selection: str
    odds_american: int
    line: float | None = None
    confidence: str = Field("medium", max_length=20)
    analysis: str = Field("", max_length=1000)


class SettlePickRequest(BaseModel):
    status: str
    profit_loss: float = 0.0


class CreateAlertRuleRequest(BaseModel):
    rule_type: str  # ev_threshold, arb_detected, line_movement, price_change
    condition_json: str = "{}"


# ── Alerts ───────────────────────────────────────────────────────────

@router.get("/alerts")
@safe_endpoint
def get_alerts(limit: int = Query(50, ge=1, le=200)):
    """Get pending edge alerts from database."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE read = 0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    alerts = [
        {
            "id": r["id"], "type": r["alert_type"], "title": r["title"],
            "message": r["message"], "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {"alerts": alerts, "count": len(alerts)}


@router.post("/alerts")
@safe_endpoint
def create_alert(alert_type: str = Query("info"), title: str = Query(...), message: str = Query("")):
    """Create a new alert."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO alerts (alert_type, title, message) VALUES (?, ?, ?)",
            (alert_type, title, message),
        )
    return {"status": "created"}


@router.delete("/alerts")
@safe_endpoint
def clear_alerts():
    """Mark all alerts as read."""
    with get_connection() as conn:
        conn.execute("UPDATE alerts SET read = 1")
    return {"cleared": True}


@router.delete("/alerts/{alert_id}")
@safe_endpoint
def dismiss_alert(alert_id: int):
    """Dismiss a single alert."""
    with get_connection() as conn:
        conn.execute("UPDATE alerts SET read = 1 WHERE id = ?", (alert_id,))
    return {"dismissed": True}


# ── Alert Rules ──────────────────────────────────────────────────────

@router.get("/alert-rules")
@safe_endpoint
def get_alert_rules(limit: int = Query(100, ge=1, le=500)):
    """Get all configured alert rules."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM alert_rules ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "rule_type": r["rule_type"],
            "condition_json": r["condition_json"],
            "enabled": bool(r["enabled"]),
            "last_triggered": r["last_triggered"],
        }
        for r in rows
    ]


@router.post("/alert-rules")
@safe_endpoint
def create_alert_rule(req: CreateAlertRuleRequest):
    """Create a new alert rule."""
    valid_types = {"ev_threshold", "arb_detected", "line_movement", "price_change"}
    if req.rule_type not in valid_types:
        raise HTTPException(400, f"rule_type must be one of: {valid_types}")

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO alert_rules (rule_type, condition_json) VALUES (?, ?)",
            (req.rule_type, req.condition_json),
        )
    return {"id": cursor.lastrowid, "status": "created"}


@router.put("/alert-rules/{rule_id}/toggle")
@safe_endpoint
def toggle_alert_rule(rule_id: int):
    """Toggle an alert rule on/off."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE alert_rules SET enabled = CASE WHEN enabled = 1 THEN 0 ELSE 1 END WHERE id = ?",
            (rule_id,),
        )
        row = conn.execute(
            "SELECT enabled FROM alert_rules WHERE id = ?", (rule_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Rule not found")
    return {"id": rule_id, "enabled": bool(row["enabled"])}


@router.delete("/alert-rules/{rule_id}")
@safe_endpoint
def delete_alert_rule(rule_id: int):
    """Delete an alert rule."""
    with get_connection() as conn:
        conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
    return {"id": rule_id, "deleted": True}


# ── Watchlist ────────────────────────────────────────────────────────

@router.get("/watchlist")
@safe_endpoint
def get_watchlist():
    """Get user's watchlisted events from database."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM watchlist ORDER BY added_at DESC"
        ).fetchall()
    items = [
        {"event_id": r["event_id"], "label": r["label"], "added_at": r["added_at"]}
        for r in rows
    ]
    return {"items": items, "count": len(items)}


@router.post("/watchlist")
@safe_endpoint
def add_to_watchlist(event_id: str = Query(...), label: str = Query("")):
    """Add an event to watchlist (persisted to DB)."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM watchlist WHERE event_id = ?", (event_id,)
        ).fetchone()
        if existing:
            return {"status": "already_exists"}
        conn.execute(
            "INSERT INTO watchlist (event_id, label) VALUES (?, ?)",
            (event_id, label),
        )
        count = conn.execute("SELECT COUNT(*) as c FROM watchlist").fetchone()["c"]
    return {"status": "added", "count": count}


@router.delete("/watchlist/{event_id}")
@safe_endpoint
def remove_from_watchlist(event_id: str):
    """Remove event from watchlist."""
    with get_connection() as conn:
        conn.execute("DELETE FROM watchlist WHERE event_id = ?", (event_id,))
        count = conn.execute("SELECT COUNT(*) as c FROM watchlist").fetchone()["c"]
    return {"status": "removed", "count": count}


# ── Leaderboard ──────────────────────────────────────────────────────

@router.get("/leaderboard")
@cached_response(ttl=300, prefix="leaderboard")
@safe_endpoint
def get_leaderboard(limit: int = Query(25, ge=1, le=100)):
    """Get the community leaderboard ranked by score."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM leaderboard ORDER BY rank_score DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        {
            "rank": i + 1,
            "username": r["username"],
            "display_name": r["display_name"],
            "total_bets": r["total_bets"],
            "wins": r["wins"],
            "losses": r["losses"],
            "win_rate": round(r["win_rate"] * 100, 1),
            "total_profit": round(r["total_profit"], 2),
            "roi_pct": round(r["roi_pct"], 1),
            "avg_odds": r["avg_odds"],
            "best_streak": r["best_streak"],
            "rank_score": round(r["rank_score"], 1),
        }
        for i, r in enumerate(rows)
    ]


@router.post("/leaderboard/register")
@safe_endpoint
def register_user(req: RegisterUserRequest):
    """Register a new user for the leaderboard."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM leaderboard WHERE username = ?", (req.username,)
        ).fetchone()
        if existing:
            return {"status": "already_exists", "username": req.username}
        conn.execute(
            "INSERT INTO leaderboard (username, display_name) VALUES (?, ?)",
            (req.username, req.display_name or req.username),
        )
    return {"status": "registered", "username": req.username}


# ── Picks ────────────────────────────────────────────────────────────

@router.post("/picks")
@safe_endpoint
def submit_pick(req: SubmitPickRequest):
    """Submit a public pick."""
    with get_connection() as conn:
        # Verify user exists
        user = conn.execute(
            "SELECT id FROM leaderboard WHERE username = ?", (req.username,)
        ).fetchone()
        if not user:
            raise HTTPException(400, "User not registered on leaderboard")

        cursor = conn.execute("""
            INSERT INTO public_picks (username, event_id, market, selection,
                                      odds_american, line, confidence, analysis)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (req.username, req.event_id, req.market, req.selection,
              req.odds_american, req.line, req.confidence, req.analysis))

    return {"id": cursor.lastrowid, "status": "submitted"}


@router.put("/picks/{pick_id}/settle")
@safe_endpoint
def settle_pick(pick_id: int, req: SettlePickRequest):
    """Settle a public pick and update the leaderboard."""
    if req.status not in ("won", "lost", "push"):
        raise HTTPException(400, "Status must be 'won', 'lost', or 'push'")

    with get_connection() as conn:
        pick = conn.execute(
            "SELECT * FROM public_picks WHERE id = ?", (pick_id,)
        ).fetchone()
        if not pick:
            raise HTTPException(404, "Pick not found")

        conn.execute(
            "UPDATE public_picks SET status = ?, profit_loss = ? WHERE id = ?",
            (req.status, req.profit_loss, pick_id),
        )

        # Update leaderboard stats
        username = pick["username"]
        lb = conn.execute(
            "SELECT * FROM leaderboard WHERE username = ?", (username,)
        ).fetchone()
        if lb:
            new_bets = lb["total_bets"] + 1
            new_wins = lb["wins"] + (1 if req.status == "won" else 0)
            new_losses = lb["losses"] + (1 if req.status == "lost" else 0)
            new_profit = lb["total_profit"] + req.profit_loss
            new_wr = new_wins / max(new_bets, 1)
            # Rank score: combines ROI, volume, and consistency
            roi = new_profit / max(new_bets * 100, 1) * 100
            rank_score = (roi * 0.4 + new_wr * 100 * 0.3 + min(new_bets, 100) * 0.3)

            conn.execute("""
                UPDATE leaderboard SET total_bets = ?, wins = ?, losses = ?,
                    total_profit = ?, win_rate = ?, roi_pct = ?, rank_score = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE username = ?
            """, (new_bets, new_wins, new_losses, round(new_profit, 2),
                  round(new_wr, 4), round(roi, 2), round(rank_score, 2), username))

    return {"pick_id": pick_id, "status": req.status}


@router.get("/picks")
@safe_endpoint
def get_picks(username: str = Query(None), limit: int = Query(50, ge=1, le=200)):
    """Get public picks, optionally filtered by username."""
    with get_connection() as conn:
        if username:
            rows = conn.execute(
                "SELECT * FROM public_picks WHERE username = ? ORDER BY created_at DESC LIMIT ?",
                (username, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM public_picks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

    return [
        {
            "id": r["id"],
            "username": r["username"],
            "event_id": r["event_id"],
            "market": r["market"],
            "selection": r["selection"],
            "odds_american": r["odds_american"],
            "line": r["line"],
            "confidence": r["confidence"],
            "analysis": r["analysis"],
            "status": r["status"],
            "profit_loss": r["profit_loss"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
