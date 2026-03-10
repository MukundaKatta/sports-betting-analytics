"""Settings, status, and health endpoints."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from sba.config import get_settings
from sba.data.db import get_connection

logger = logging.getLogger(__name__)
router = APIRouter(tags=["settings"])


# ── Pydantic models ─────────────────────────────────────────────────

class StatusResponse(BaseModel):
    events: int
    odds_snapshots: int
    players: int
    game_logs: int
    bets: int
    api_credits: int | None


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime: str
    database: str


class SettingsResponse(BaseModel):
    bankroll: float
    kelly_fraction: float
    ev_threshold: float
    default_sport: str
    refresh_interval: int


class UpdateSettingsRequest(BaseModel):
    bankroll: float | None = None
    kelly_fraction: float | None = None
    ev_threshold: float | None = None
    default_sport: str | None = None
    refresh_interval: int | None = None


# ── Module-level state ──────────────────────────────────────────────

_start_time = datetime.now()


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint for monitoring."""
    uptime = datetime.now() - _start_time
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    db_status = "healthy"
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
    except Exception:
        db_status = "unhealthy"

    return HealthResponse(
        status="ok",
        version="2.0.0",
        uptime=f"{hours}h {minutes}m {seconds}s",
        database=db_status,
    )


@router.get("/status", response_model=StatusResponse)
def get_status():
    """Get database and API status."""
    with get_connection() as conn:
        events = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
        snapshots = conn.execute("SELECT COUNT(*) as c FROM odds_snapshots").fetchone()["c"]
        players = conn.execute("SELECT COUNT(*) as c FROM players").fetchone()["c"]
        logs = conn.execute("SELECT COUNT(*) as c FROM player_game_logs").fetchone()["c"]
        bets = conn.execute("SELECT COUNT(*) as c FROM bets").fetchone()["c"]

    return StatusResponse(
        events=events,
        odds_snapshots=snapshots,
        players=players,
        game_logs=logs,
        bets=bets,
        api_credits=None,
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings_endpoint():
    """Get current app settings."""
    settings = get_settings()
    return SettingsResponse(
        bankroll=settings.BANKROLL,
        kelly_fraction=settings.KELLY_FRACTION,
        ev_threshold=settings.EV_THRESHOLD,
        default_sport=settings.DEFAULT_SPORT,
        refresh_interval=settings.REFRESH_INTERVAL_SECONDS,
    )


@router.put("/settings")
def update_settings_endpoint(req: UpdateSettingsRequest):
    """Update app settings (runtime only, not persisted to .env)."""
    import os

    updates = {}
    if req.bankroll is not None:
        os.environ["BANKROLL"] = str(req.bankroll)
        updates["bankroll"] = req.bankroll
    if req.kelly_fraction is not None:
        os.environ["KELLY_FRACTION"] = str(req.kelly_fraction)
        updates["kelly_fraction"] = req.kelly_fraction
    if req.ev_threshold is not None:
        os.environ["EV_THRESHOLD"] = str(req.ev_threshold)
        updates["ev_threshold"] = req.ev_threshold
    if req.default_sport is not None:
        os.environ["DEFAULT_SPORT"] = req.default_sport
        updates["default_sport"] = req.default_sport
    if req.refresh_interval is not None:
        os.environ["REFRESH_INTERVAL_SECONDS"] = str(req.refresh_interval)
        updates["refresh_interval"] = req.refresh_interval

    # Clear settings cache so next get_settings() picks up changes
    get_settings.cache_clear()
    return {"updated": updates}
