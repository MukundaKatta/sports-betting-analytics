"""REST API endpoints for the web dashboard."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from sba.config import get_settings
from sba.data.db import get_connection, init_db
from sba.data.db.repository import Repository

logger = logging.getLogger(__name__)
router = APIRouter(tags=["api"])
repo = Repository()


# ── Pydantic response models ──────────────────────────────────────────

class EventResponse(BaseModel):
    id: str
    sport: str
    home_team: str
    away_team: str
    commence_time: str
    completed: bool
    home_score: int | None = None
    away_score: int | None = None


class EdgeResponse(BaseModel):
    event_home: str
    event_away: str
    event_id: str
    market: str
    selection: str
    line: float | None
    best_odds_american: int
    best_odds_decimal: float
    bookmaker: str
    model_prob: float
    implied_prob: float
    ev: float
    ev_pct: str
    kelly_pct: float
    recommended_stake: float
    confidence: str


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


class BetResponse(BaseModel):
    id: int | None
    event_id: str
    market: str
    selection: str
    line: float | None
    odds_american: int
    odds_decimal: float
    model_probability: float
    expected_value: float
    kelly_fraction: float
    recommended_stake: float
    bookmaker: str
    status: str
    profit_loss: float
    placed_at: str | None


class BetSummaryResponse(BaseModel):
    total_bets: int
    wins: int
    losses: int
    pushes: int
    pending: int
    win_rate: float
    total_staked: float
    total_profit: float
    roi: float
    bets: list[BetResponse]


class PlayerProfileResponse(BaseModel):
    name: str
    team: str
    position: str
    games: int
    last_5: dict[str, float]
    last_20: dict[str, float]
    trends: dict[str, float]
    recent_games: list[dict]


class StatusResponse(BaseModel):
    events: int
    odds_snapshots: int
    players: int
    game_logs: int
    bets: int
    api_credits: int | None


# ── API Endpoints ─────────────────────────────────────────────────────

@router.get("/edges", response_model=list[EdgeResponse])
def get_edges(
    sport: str = Query(None),
    market: str = Query("h2h,spreads,totals"),
    min_ev: float = Query(None),
):
    """Scan for +EV betting opportunities."""
    settings = get_settings()
    if not settings.ODDS_API_KEY:
        raise HTTPException(400, "ODDS_API_KEY not configured")

    from sba.services.edge_finder import EdgeFinder

    finder = EdgeFinder()
    opportunities = finder.scan(sport, market, min_ev)

    return [
        EdgeResponse(
            event_home=o.event.home_team,
            event_away=o.event.away_team,
            event_id=o.event.id,
            market=o.market,
            selection=o.selection,
            line=o.line,
            best_odds_american=o.best_odds.price_american,
            best_odds_decimal=o.best_odds.price_decimal,
            bookmaker=o.bookmaker,
            model_prob=round(o.model_prob, 4),
            implied_prob=round(o.implied_prob, 4),
            ev=round(o.ev, 4),
            ev_pct=f"{o.ev * 100:+.1f}%",
            kelly_pct=round(o.kelly_pct, 4),
            recommended_stake=round(o.recommended_stake, 2),
            confidence=o.confidence,
        )
        for o in opportunities
    ]


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


@router.get("/events", response_model=list[EventResponse])
def get_events(sport: str = Query(None)):
    """Get upcoming events from the database."""
    settings = get_settings()
    sport = sport or settings.DEFAULT_SPORT
    with get_connection() as conn:
        events = repo.get_upcoming_events(conn, sport)
    return [
        EventResponse(
            id=e.id, sport=e.sport,
            home_team=e.home_team, away_team=e.away_team,
            commence_time=e.commence_time.isoformat(),
            completed=e.completed,
            home_score=e.home_score, away_score=e.away_score,
        )
        for e in events
    ]


@router.get("/bets", response_model=BetSummaryResponse)
def get_bets():
    """Get bet history and summary stats."""
    init_db()
    with get_connection() as conn:
        bets = repo.get_bet_history(conn)

    settled = [b for b in bets if b.status in ("won", "lost", "push")]
    pending = [b for b in bets if b.status == "pending"]
    wins = sum(1 for b in settled if b.status == "won")
    losses = sum(1 for b in settled if b.status == "lost")
    pushes = sum(1 for b in settled if b.status == "push")
    total_staked = sum(b.recommended_stake for b in settled)
    total_profit = sum(b.profit_loss for b in settled)
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0

    return BetSummaryResponse(
        total_bets=len(settled),
        wins=wins,
        losses=losses,
        pushes=pushes,
        pending=len(pending),
        win_rate=wins / max(len(settled), 1),
        total_staked=round(total_staked, 2),
        total_profit=round(total_profit, 2),
        roi=round(roi, 2),
        bets=[
            BetResponse(
                id=b.id, event_id=b.event_id, market=b.market,
                selection=b.selection, line=b.line,
                odds_american=b.odds_american, odds_decimal=b.odds_decimal,
                model_probability=b.model_probability,
                expected_value=b.expected_value,
                kelly_fraction=b.kelly_fraction,
                recommended_stake=b.recommended_stake,
                bookmaker=b.bookmaker, status=b.status,
                profit_loss=b.profit_loss,
                placed_at=b.placed_at.isoformat() if b.placed_at else None,
            )
            for b in bets
        ],
    )


class TrackBetRequest(BaseModel):
    event_id: str
    market: str
    selection: str
    odds_american: int
    stake: float = 0
    line: float | None = None
    bookmaker: str = "manual"


@router.post("/bets/track")
def track_bet(req: TrackBetRequest):
    """Track a new bet."""
    from sba.utils.odds_math import american_to_decimal
    from sba.models.domain import TrackedBet

    init_db()
    bet = TrackedBet(
        event_id=req.event_id, market=req.market, selection=req.selection,
        line=req.line, odds_american=req.odds_american,
        odds_decimal=american_to_decimal(req.odds_american),
        model_probability=0, expected_value=0,
        kelly_fraction=0, recommended_stake=req.stake,
        bookmaker=req.bookmaker,
    )
    with get_connection() as conn:
        bet_id = repo.insert_bet(conn, bet)
    return {"id": bet_id, "status": "tracked"}


@router.get("/players/{name}", response_model=PlayerProfileResponse | None)
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


@router.get("/status", response_model=StatusResponse)
def get_status():
    """Get database and API status."""
    init_db()
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


@router.get("/line-movement/{event_id}")
def get_line_movement(event_id: str, market: str = Query("h2h")):
    """Get line movement history for an event."""
    with get_connection() as conn:
        snapshots = repo.get_odds_history(conn, event_id, market)
    return [
        {
            "time": str(s.snapshot_time)[:19] if s.snapshot_time else "",
            "bookmaker": s.bookmaker,
            "outcome": s.outcome_name,
            "line": s.outcome_point,
            "odds_american": s.price_american,
            "odds_decimal": s.price_decimal,
        }
        for s in snapshots
    ]
