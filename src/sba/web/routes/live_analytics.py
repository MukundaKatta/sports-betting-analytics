"""Live/in-play betting analytics API routes.

Real-time game analysis, momentum tracking, odds velocity,
and live edge signals. Inspired by Outlier React Live.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from sba.services.live_analytics import (
    get_live_game_analysis,
    get_live_games_summary,
    get_odds_velocity,
)

from sba.web.errors import safe_endpoint

router = APIRouter(tags=["live-analytics"])


@router.get("/live/games")
@safe_endpoint
def api_live_games():
    """Get summary of all currently active games."""
    return get_live_games_summary()


@router.get("/live/game/{event_id}")
@safe_endpoint
def api_live_game_analysis(event_id: str):
    """Get real-time analysis for a specific live game.

    Returns momentum, line movements, and actionable signals.
    """
    return get_live_game_analysis(event_id)


@router.get("/live/velocity/{event_id}")
@safe_endpoint
def api_odds_velocity(
    event_id: str,
    window: int = Query(15, ge=5, le=120, description="Window in minutes"),
):
    """Measure odds velocity (rate of change) for an event.

    Higher velocity = more market activity = sharper attention needed.
    """
    return get_odds_velocity(event_id, window)
