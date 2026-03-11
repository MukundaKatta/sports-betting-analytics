"""Responsible gambling API routes.

Provides deposit/loss/wager limits, session tracking, behavioral analysis,
and cooldown/self-exclusion features. Becoming a regulatory requirement
in multiple US jurisdictions.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from sba.services.responsible_gambling import (
    check_cooldown,
    check_limits,
    end_session,
    get_behavioral_report,
    get_limits,
    get_session_stats,
    remove_limit,
    set_cooldown,
    set_limit,
    start_session,
)

router = APIRouter(tags=["responsible-gambling"])


# ── Limits ──────────────────────────────────────────────────────────

@router.get("/rg/limits")
def api_get_limits():
    """Get all configured responsible gambling limits."""
    return get_limits()


class SetLimitRequest(BaseModel):
    limit_type: str
    amount: float
    period: str = "daily"


@router.post("/rg/limits")
def api_set_limit(req: SetLimitRequest):
    """Set or update a responsible gambling limit."""
    result = set_limit(req.limit_type, req.amount, req.period)
    if "error" in result:
        raise HTTPException(422, result["error"])
    return result


@router.delete("/rg/limits")
def api_remove_limit(
    limit_type: str = Query(..., description="deposit, loss, wager, or session_minutes"),
    period: str = Query("daily"),
):
    """Remove a responsible gambling limit."""
    return remove_limit(limit_type, period)


@router.get("/rg/limits/check")
def api_check_limits():
    """Check current usage against all configured limits."""
    return check_limits()


# ── Sessions ────────────────────────────────────────────────────────

@router.post("/rg/sessions/start")
def api_start_session():
    """Start a new betting session for time tracking."""
    return start_session()


@router.post("/rg/sessions/end")
def api_end_session():
    """End the current betting session."""
    result = end_session()
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/rg/sessions")
def api_session_stats():
    """Get session history and statistics."""
    return get_session_stats()


# ── Behavioral Analysis ────────────────────────────────────────────

@router.get("/rg/behavior")
def api_behavioral_report():
    """Analyze betting behavior for problem gambling indicators."""
    return get_behavioral_report()


# ── Cooldown ────────────────────────────────────────────────────────

class CooldownRequest(BaseModel):
    hours: int


@router.post("/rg/cooldown")
def api_set_cooldown(req: CooldownRequest):
    """Set a mandatory cooldown period."""
    result = set_cooldown(req.hours)
    if "error" in result:
        raise HTTPException(422, result["error"])
    return result


@router.get("/rg/cooldown")
def api_check_cooldown():
    """Check if a cooldown is currently active."""
    return check_cooldown()


@router.get("/responsible-gambling/status")
def responsible_gambling_status():
    """Get current responsible gambling limits and status."""
    from sba.data.db import get_connection, init_db

    init_db()
    with get_connection() as conn:
        today_bets = conn.execute("""
            SELECT COUNT(*) as count,
                   COALESCE(SUM(recommended_stake), 0) as total_staked,
                   COALESCE(SUM(profit_loss), 0) as total_pnl
            FROM bets WHERE DATE(placed_at) = DATE('now')
        """).fetchone()

        week_bets = conn.execute("""
            SELECT COUNT(*) as count,
                   COALESCE(SUM(recommended_stake), 0) as total_staked,
                   COALESCE(SUM(profit_loss), 0) as total_pnl
            FROM bets WHERE placed_at >= DATE('now', '-7 days')
        """).fetchone()

        month_bets = conn.execute("""
            SELECT COUNT(*) as count,
                   COALESCE(SUM(recommended_stake), 0) as total_staked,
                   COALESCE(SUM(profit_loss), 0) as total_pnl
            FROM bets WHERE placed_at >= DATE('now', '-30 days')
        """).fetchone()

        bankroll = conn.execute(
            "SELECT amount FROM bankroll_log ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        current_bankroll = bankroll["amount"] if bankroll else 0

    daily_loss_limit = current_bankroll * 0.05
    weekly_loss_limit = current_bankroll * 0.15
    daily_bet_limit = 20
    max_stake_pct = 5.0

    today_loss = min(0, today_bets["total_pnl"])
    week_loss = min(0, week_bets["total_pnl"])

    alerts = []
    if abs(today_loss) > daily_loss_limit * 0.8 and daily_loss_limit > 0:
        alerts.append({
            "level": "warning" if abs(today_loss) < daily_loss_limit else "critical",
            "message": f"Daily loss ${abs(today_loss):.0f} approaching limit ${daily_loss_limit:.0f}",
        })
    if abs(week_loss) > weekly_loss_limit * 0.8 and weekly_loss_limit > 0:
        alerts.append({
            "level": "warning" if abs(week_loss) < weekly_loss_limit else "critical",
            "message": f"Weekly loss ${abs(week_loss):.0f} approaching limit ${weekly_loss_limit:.0f}",
        })
    if today_bets["count"] >= daily_bet_limit:
        alerts.append({"level": "warning", "message": f"Daily bet limit reached ({daily_bet_limit})"})

    losing_streak = 0
    with get_connection() as conn:
        recent = conn.execute(
            "SELECT status FROM bets ORDER BY placed_at DESC LIMIT 20"
        ).fetchall()
    for r in recent:
        if r["status"] == "lost":
            losing_streak += 1
        else:
            break
    if losing_streak >= 5:
        alerts.append({"level": "warning", "message": f"On a {losing_streak}-bet losing streak"})

    return {
        "today": {"bets": today_bets["count"], "staked": round(today_bets["total_staked"], 2), "pnl": round(today_bets["total_pnl"], 2)},
        "week": {"bets": week_bets["count"], "staked": round(week_bets["total_staked"], 2), "pnl": round(week_bets["total_pnl"], 2)},
        "month": {"bets": month_bets["count"], "staked": round(month_bets["total_staked"], 2), "pnl": round(month_bets["total_pnl"], 2)},
        "limits": {
            "daily_loss": round(daily_loss_limit, 2),
            "weekly_loss": round(weekly_loss_limit, 2),
            "daily_bets": daily_bet_limit,
            "max_stake_pct": max_stake_pct,
        },
        "current_bankroll": round(current_bankroll, 2),
        "losing_streak": losing_streak,
        "alerts": alerts,
        "resources": [
            {"name": "National Problem Gambling Helpline", "contact": "1-800-522-4700"},
            {"name": "Gamblers Anonymous", "url": "https://www.gamblersanonymous.org"},
            {"name": "National Council on Problem Gambling", "url": "https://www.ncpgambling.org"},
        ],
    }
