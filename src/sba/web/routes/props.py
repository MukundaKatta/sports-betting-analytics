"""Player props, player search, and player profiles endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from sba.config import get_settings
from sba.data.db import get_connection

logger = logging.getLogger(__name__)
router = APIRouter(tags=["props"])


# ── Pydantic models ─────────────────────────────────────────────────

class PropResponse(BaseModel):
    player_name: str
    player_team: str
    market: str
    predicted_value: float
    line: float
    over_prob: float
    under_prob: float
    over_ev: float
    under_ev: float
    over_odds_american: int | None = None
    under_odds_american: int | None = None
    recommendation: str
    top_features: list[str]


class PlayerProfileResponse(BaseModel):
    name: str
    team: str
    position: str
    games: int
    last_5: dict[str, float]
    last_20: dict[str, float]
    trends: dict[str, float]
    recent_games: list[dict]


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/props", response_model=list[PropResponse])
def get_props(
    sport: str = Query(None),
    event_id: str = Query(None),
    markets: str = Query("player_points,player_rebounds,player_assists"),
):
    """Scan for +EV player prop opportunities."""
    settings = get_settings()
    if not settings.ODDS_API_KEY:
        raise HTTPException(400, "ODDS_API_KEY not configured")

    from sba.services.prop_analyzer import PropAnalyzer

    analyzer = PropAnalyzer()
    market_list = [m.strip() for m in markets.split(",")]
    predictions = analyzer.analyze(sport, event_id, market_list)

    return [
        PropResponse(
            player_name=p.player.name,
            player_team=p.player.team,
            market=p.market.replace("player_", "").replace("_", " ").title(),
            predicted_value=round(p.predicted_value, 1),
            line=p.line,
            over_prob=round(p.over_prob, 4),
            under_prob=round(p.under_prob, 4),
            over_ev=round(p.over_ev, 4),
            under_ev=round(p.under_ev, 4),
            over_odds_american=p.best_over_odds.price_american if p.best_over_odds else None,
            under_odds_american=p.best_under_odds.price_american if p.best_under_odds else None,
            recommendation=p.recommendation,
            top_features=p.top_features,
        )
        for p in predictions
    ]


@router.get("/search/players")
def search_players(q: str = Query(..., min_length=2)):
    """Search for players by name prefix."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name, team, position FROM players WHERE LOWER(name) LIKE ? LIMIT 10",
            (f"%{q.lower()}%",),
        ).fetchall()
    return [{"name": r["name"], "team": r["team"], "position": r["position"]} for r in rows]


@router.get("/players/{name}", response_model=Optional[PlayerProfileResponse])
def get_player(name: str):
    """Get player profile and recent stats."""
    from sba.services.prop_analyzer import PropAnalyzer

    analyzer = PropAnalyzer()
    profile = analyzer.player_profile(name)
    if not profile:
        raise HTTPException(404, f"Player '{name}' not found")

    return PlayerProfileResponse(
        name=profile["player"].name,
        team=profile["player"].team,
        position=profile["player"].position,
        games=profile["games"],
        last_5=profile["last_5"],
        last_20=profile["last_20"],
        trends=profile["trends"],
        recent_games=[
            {
                "date": str(log.game_date),
                "opponent": log.opponent,
                "minutes": log.minutes,
                "points": log.points,
                "rebounds": log.rebounds,
                "assists": log.assists,
                "threes": log.threes,
                "steals": log.steals,
                "blocks": log.blocks,
            }
            for log in profile["recent_games"][:10]
        ],
    )
