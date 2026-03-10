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
