"""REST API endpoints for the web dashboard."""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
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


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime: str
    database: str


class AnalyticsResponse(BaseModel):
    by_market: dict[str, dict]
    by_bookmaker: dict[str, dict]
    daily_pnl: list[dict]
    best_bet: dict | None
    worst_bet: dict | None
    streak: dict


class SettingsResponse(BaseModel):
    bankroll: float
    kelly_fraction: float
    ev_threshold: float
    default_sport: str
    refresh_interval: int


class TrackBetRequest(BaseModel):
    event_id: str
    market: str
    selection: str
    odds_american: int
    stake: float = 0
    line: float | None = None
    bookmaker: str = "manual"


class SettleBetRequest(BaseModel):
    status: str
    profit_loss: float


class UpdateSettingsRequest(BaseModel):
    bankroll: float | None = None
    kelly_fraction: float | None = None
    ev_threshold: float | None = None
    default_sport: str | None = None
    refresh_interval: int | None = None


# ── Health & Status ─────────────────────────────────────────────

_start_time = datetime.now()


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint for monitoring."""
    uptime = datetime.now() - _start_time
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    db_status = "healthy"
    try:
        init_db()
        with get_connection() as conn:
            conn.execute("SELECT 1")
    except Exception:
        db_status = "unhealthy"

    return HealthResponse(
        status="ok",
        version="0.5.0",
        uptime=f"{hours}h {minutes}m {seconds}s",
        database=db_status,
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


# ── Edge Finding ─────────────────────────────────────────────────────

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


# ── Player Props ─────────────────────────────────────────────────────

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


# ── Events ───────────────────────────────────────────────────────────

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


# ── Bet Tracking & Management ────────────────────────────────────────

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


@router.put("/bets/{bet_id}/settle")
def settle_bet(bet_id: int, req: SettleBetRequest):
    """Settle a bet with result."""
    if req.status not in ("won", "lost", "push"):
        raise HTTPException(400, "Status must be 'won', 'lost', or 'push'")

    init_db()
    with get_connection() as conn:
        repo.update_bet_result(conn, bet_id, req.status, req.profit_loss)
    return {"id": bet_id, "status": req.status, "profit_loss": req.profit_loss}


@router.delete("/bets/{bet_id}")
def delete_bet(bet_id: int):
    """Delete a tracked bet."""
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM bets WHERE id = ?", (bet_id,))
    return {"id": bet_id, "deleted": True}


@router.get("/bets/export")
def export_bets_csv():
    """Export bet history as CSV file."""
    init_db()
    with get_connection() as conn:
        bets = repo.get_bet_history(conn)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Date", "Event", "Market", "Selection", "Line",
        "Odds (American)", "Odds (Decimal)", "Stake", "Bookmaker",
        "Status", "P/L", "Model Prob", "EV", "Kelly %",
    ])
    for b in bets:
        writer.writerow([
            b.id,
            b.placed_at.isoformat() if b.placed_at else "",
            b.event_id, b.market, b.selection, b.line or "",
            b.odds_american, f"{b.odds_decimal:.3f}",
            f"{b.recommended_stake:.2f}", b.bookmaker,
            b.status, f"{b.profit_loss:.2f}",
            f"{b.model_probability:.4f}", f"{b.expected_value:.4f}",
            f"{b.kelly_fraction:.4f}",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sba_bets_export.csv"},
    )


# ── Search ──────────────────────────────────────────────────────────

@router.get("/search/players")
def search_players(q: str = Query(..., min_length=2)):
    """Search for players by name prefix."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name, team, position FROM players WHERE LOWER(name) LIKE ? LIMIT 10",
            (f"%{q.lower()}%",),
        ).fetchall()
    return [{"name": r["name"], "team": r["team"], "position": r["position"]} for r in rows]


# ── Analytics ────────────────────────────────────────────────────────

@router.get("/analytics", response_model=AnalyticsResponse)
def get_analytics():
    """Get detailed betting analytics breakdown."""
    init_db()
    with get_connection() as conn:
        bets = repo.get_bet_history(conn)

    settled = [b for b in bets if b.status in ("won", "lost", "push")]

    # Analytics by market
    by_market: dict[str, dict] = {}
    for b in settled:
        m = b.market
        if m not in by_market:
            by_market[m] = {"bets": 0, "wins": 0, "profit": 0.0, "staked": 0.0}
        by_market[m]["bets"] += 1
        if b.status == "won":
            by_market[m]["wins"] += 1
        by_market[m]["profit"] += b.profit_loss
        by_market[m]["staked"] += b.recommended_stake

    for m in by_market:
        by_market[m]["win_rate"] = round(by_market[m]["wins"] / max(by_market[m]["bets"], 1) * 100, 1)
        by_market[m]["roi"] = round(by_market[m]["profit"] / max(by_market[m]["staked"], 1) * 100, 1)
        by_market[m]["profit"] = round(by_market[m]["profit"], 2)
        by_market[m]["staked"] = round(by_market[m]["staked"], 2)

    # Analytics by bookmaker
    by_bookmaker: dict[str, dict] = {}
    for b in settled:
        bk = b.bookmaker
        if bk not in by_bookmaker:
            by_bookmaker[bk] = {"bets": 0, "wins": 0, "profit": 0.0, "staked": 0.0}
        by_bookmaker[bk]["bets"] += 1
        if b.status == "won":
            by_bookmaker[bk]["wins"] += 1
        by_bookmaker[bk]["profit"] += b.profit_loss
        by_bookmaker[bk]["staked"] += b.recommended_stake

    for bk in by_bookmaker:
        by_bookmaker[bk]["win_rate"] = round(by_bookmaker[bk]["wins"] / max(by_bookmaker[bk]["bets"], 1) * 100, 1)
        by_bookmaker[bk]["roi"] = round(by_bookmaker[bk]["profit"] / max(by_bookmaker[bk]["staked"], 1) * 100, 1)
        by_bookmaker[bk]["profit"] = round(by_bookmaker[bk]["profit"], 2)
        by_bookmaker[bk]["staked"] = round(by_bookmaker[bk]["staked"], 2)

    # Daily P/L timeline
    daily_pnl: dict[str, float] = {}
    for b in settled:
        if b.placed_at:
            day = b.placed_at.strftime("%Y-%m-%d")
            daily_pnl[day] = round(daily_pnl.get(day, 0) + b.profit_loss, 2)

    daily_pnl_list = [{"date": d, "pnl": v} for d, v in sorted(daily_pnl.items())]

    # Best and worst bets
    best = max(settled, key=lambda b: b.profit_loss) if settled else None
    worst = min(settled, key=lambda b: b.profit_loss) if settled else None

    def bet_summary(b):
        return {
            "selection": b.selection, "market": b.market,
            "odds": b.odds_american, "profit_loss": round(b.profit_loss, 2),
            "bookmaker": b.bookmaker,
        }

    # Current streak
    streak_type = ""
    streak_count = 0
    for b in sorted(settled, key=lambda x: x.placed_at or datetime.min, reverse=True):
        if not streak_type:
            streak_type = b.status
            streak_count = 1
        elif b.status == streak_type:
            streak_count += 1
        else:
            break

    return AnalyticsResponse(
        by_market=by_market,
        by_bookmaker=by_bookmaker,
        daily_pnl=daily_pnl_list,
        best_bet=bet_summary(best) if best else None,
        worst_bet=bet_summary(worst) if worst else None,
        streak={"type": streak_type, "count": streak_count},
    )


# ── Players ──────────────────────────────────────────────────────────

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


# ── Line Movement ───────────────────────────────────────────────────

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


# ── Settings ─────────────────────────────────────────────────────────

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


# ── Odds Comparison ─────────────────────────────────────────────────

@router.get("/odds-comparison/{event_id}")
def get_odds_comparison(event_id: str, market: str = Query("h2h")):
    """Get latest odds from all bookmakers for an event, grouped by outcome."""
    with get_connection() as conn:
        snapshots = repo.get_odds_history(conn, event_id, market)

    # Group by bookmaker+outcome, keep only latest snapshot per group
    latest: dict[str, dict] = {}
    for s in snapshots:
        key = f"{s.bookmaker}|{s.outcome_name}"
        latest[key] = {
            "bookmaker": s.bookmaker,
            "outcome": s.outcome_name,
            "line": s.outcome_point,
            "odds_american": s.price_american,
            "odds_decimal": s.price_decimal,
            "time": str(s.snapshot_time)[:19] if s.snapshot_time else "",
        }

    # Organize into matrix: outcomes as rows, bookmakers as columns
    outcomes: dict[str, list] = {}
    bookmakers = set()
    for entry in latest.values():
        outcome = entry["outcome"]
        bk = entry["bookmaker"]
        bookmakers.add(bk)
        if outcome not in outcomes:
            outcomes[outcome] = []
        outcomes[outcome].append(entry)

    return {
        "bookmakers": sorted(bookmakers),
        "outcomes": outcomes,
        "total_snapshots": len(snapshots),
    }


# ── Notifications / Alerts ──────────────────────────────────────────

_alerts: list[dict] = []


@router.get("/alerts")
def get_alerts():
    """Get pending edge alerts."""
    return {"alerts": _alerts, "count": len(_alerts)}


@router.delete("/alerts")
def clear_alerts():
    """Clear all alerts."""
    _alerts.clear()
    return {"cleared": True}


# ── Bankroll Simulator ─────────────────────────────────────────────

class SimulationRequest(BaseModel):
    bankroll: float = 1000
    num_bets: int = 100
    avg_odds: int = -110
    win_rate: float = 0.53
    kelly_fraction: float = 0.25
    simulations: int = 50


@router.post("/simulate")
def run_simulation(req: SimulationRequest):
    """Run Monte Carlo bankroll simulation."""
    import random

    random.seed(42)
    results = []

    # Convert American odds to decimal payout
    if req.avg_odds > 0:
        payout_mult = req.avg_odds / 100
    else:
        payout_mult = 100 / abs(req.avg_odds)

    for _ in range(req.simulations):
        bankroll = req.bankroll
        path = [bankroll]
        for _ in range(req.num_bets):
            stake = bankroll * req.kelly_fraction * 0.1  # scaled kelly
            if stake <= 0:
                path.append(bankroll)
                continue
            if random.random() < req.win_rate:
                bankroll += stake * payout_mult
            else:
                bankroll -= stake
            path.append(round(bankroll, 2))
        results.append(path)

    # Calculate percentiles
    num_steps = req.num_bets + 1
    p10 = []
    p25 = []
    p50 = []
    p75 = []
    p90 = []
    for i in range(num_steps):
        vals = sorted(r[i] for r in results)
        n = len(vals)
        p10.append(round(vals[int(n * 0.1)], 2))
        p25.append(round(vals[int(n * 0.25)], 2))
        p50.append(round(vals[int(n * 0.5)], 2))
        p75.append(round(vals[int(n * 0.75)], 2))
        p90.append(round(vals[int(n * 0.9)], 2))

    final_values = [r[-1] for r in results]
    profitable = sum(1 for v in final_values if v > req.bankroll)

    return {
        "percentiles": {"p10": p10, "p25": p25, "p50": p50, "p75": p75, "p90": p90},
        "summary": {
            "median_final": round(p50[-1], 2),
            "best_case": round(max(final_values), 2),
            "worst_case": round(min(final_values), 2),
            "profitable_pct": round(profitable / req.simulations * 100, 1),
            "median_roi": round((p50[-1] - req.bankroll) / req.bankroll * 100, 1),
        },
        "simulations": req.simulations,
        "num_bets": req.num_bets,
    }


# ── Live Odds Feed ─────────────────────────────────────────────────

@router.get("/live-odds")
def get_live_odds(limit: int = Query(20)):
    """Get most recent odds snapshots as a live feed."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT os.bookmaker, os.outcome_name, os.price_american, os.price_decimal,
                   os.outcome_point, os.snapshot_time,
                   e.home_team, e.away_team, e.sport, os.market
            FROM odds_snapshots os
            JOIN events e ON os.event_id = e.id
            ORDER BY os.snapshot_time DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [
        {
            "bookmaker": r["bookmaker"],
            "outcome": r["outcome_name"],
            "odds_american": r["price_american"],
            "odds_decimal": round(r["price_decimal"], 3),
            "line": r["outcome_point"],
            "time": str(r["snapshot_time"])[:19] if r["snapshot_time"] else "",
            "home_team": r["home_team"],
            "away_team": r["away_team"],
            "sport": r["sport"],
            "market": r["market"],
        }
        for r in rows
    ]


# ── Advanced Analytics / Performance Metrics ──────────────────────

@router.get("/analytics/advanced")
def get_advanced_analytics():
    """Get advanced performance metrics: Sharpe, max drawdown, CLV, streaks."""
    import math

    init_db()
    with get_connection() as conn:
        bets = repo.get_bet_history(conn)

    settled = sorted(
        [b for b in bets if b.status in ("won", "lost", "push")],
        key=lambda x: x.placed_at or datetime.min,
    )

    if not settled:
        return {
            "sharpe_ratio": 0, "max_drawdown": 0, "max_drawdown_pct": 0,
            "avg_odds": 0, "avg_ev": 0, "clv_avg": 0,
            "longest_win_streak": 0, "longest_loss_streak": 0,
            "profit_factor": 0, "avg_stake": 0,
            "cumulative_pnl": [], "drawdown_series": [],
            "monthly_breakdown": [], "hourly_distribution": [],
            "unit_size_analysis": {},
        }

    # Cumulative P/L series
    pnl_list = [b.profit_loss for b in settled]
    cumulative = []
    running = 0
    for p in pnl_list:
        running += p
        cumulative.append(round(running, 2))

    # Max drawdown
    peak = 0
    max_dd = 0
    dd_series = []
    for val in cumulative:
        peak = max(peak, val)
        dd = peak - val
        max_dd = max(max_dd, dd)
        dd_series.append(round(dd, 2))

    # Sharpe ratio (annualized assuming ~1 bet/day)
    if len(pnl_list) >= 2:
        mean_pnl = sum(pnl_list) / len(pnl_list)
        variance = sum((x - mean_pnl) ** 2 for x in pnl_list) / (len(pnl_list) - 1)
        std_pnl = math.sqrt(variance) if variance > 0 else 1
        sharpe = (mean_pnl / std_pnl) * math.sqrt(365)
    else:
        sharpe = 0

    # Streaks
    longest_win = longest_loss = current_streak = 0
    current_type = ""
    for b in settled:
        if b.status == current_type:
            current_streak += 1
        else:
            current_type = b.status
            current_streak = 1
        if current_type == "won":
            longest_win = max(longest_win, current_streak)
        elif current_type == "lost":
            longest_loss = max(longest_loss, current_streak)

    # Profit factor
    gross_profit = sum(b.profit_loss for b in settled if b.profit_loss > 0)
    gross_loss = abs(sum(b.profit_loss for b in settled if b.profit_loss < 0))
    profit_factor = round(gross_profit / max(gross_loss, 0.01), 2)

    # Average CLV (closing line value) approximation
    avg_ev = round(
        sum(b.expected_value for b in settled) / max(len(settled), 1) * 100, 2
    )

    # Monthly breakdown
    monthly: dict[str, dict] = {}
    for b in settled:
        if b.placed_at:
            month = b.placed_at.strftime("%Y-%m")
            if month not in monthly:
                monthly[month] = {"bets": 0, "profit": 0, "staked": 0}
            monthly[month]["bets"] += 1
            monthly[month]["profit"] = round(monthly[month]["profit"] + b.profit_loss, 2)
            monthly[month]["staked"] = round(monthly[month]["staked"] + b.recommended_stake, 2)
    monthly_list = [
        {
            "month": m,
            "bets": d["bets"],
            "profit": d["profit"],
            "roi": round(d["profit"] / max(d["staked"], 0.01) * 100, 1),
        }
        for m, d in sorted(monthly.items())
    ]

    # Avg stake and odds
    avg_stake = round(
        sum(b.recommended_stake for b in settled) / max(len(settled), 1), 2
    )
    avg_odds = round(
        sum(b.odds_american for b in settled) / max(len(settled), 1)
    )

    total_staked = sum(b.recommended_stake for b in settled)
    max_dd_pct = round(max_dd / max(total_staked, 0.01) * 100, 1)

    return {
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": max_dd_pct,
        "avg_odds": avg_odds,
        "avg_ev": avg_ev,
        "clv_avg": avg_ev,
        "longest_win_streak": longest_win,
        "longest_loss_streak": longest_loss,
        "profit_factor": profit_factor,
        "avg_stake": avg_stake,
        "cumulative_pnl": cumulative,
        "drawdown_series": dd_series,
        "monthly_breakdown": monthly_list,
    }


# ── Favorites / Watchlist ─────────────────────────────────────────

_watchlist: list[dict] = []


@router.get("/watchlist")
def get_watchlist():
    """Get user's watchlisted events."""
    return {"items": _watchlist, "count": len(_watchlist)}


@router.post("/watchlist")
def add_to_watchlist(event_id: str = Query(...), label: str = Query("")):
    """Add an event to watchlist."""
    if any(w["event_id"] == event_id for w in _watchlist):
        return {"status": "already_exists"}
    _watchlist.append({
        "event_id": event_id,
        "label": label,
        "added_at": datetime.now().isoformat(),
    })
    return {"status": "added", "count": len(_watchlist)}


@router.delete("/watchlist/{event_id}")
def remove_from_watchlist(event_id: str):
    """Remove event from watchlist."""
    global _watchlist
    _watchlist = [w for w in _watchlist if w["event_id"] != event_id]
    return {"status": "removed", "count": len(_watchlist)}


# ── Bet Calculator ────────────────────────────────────────────────

class CalcRequest(BaseModel):
    odds_american: int | None = None
    odds_decimal: float | None = None
    odds_fractional: str | None = None
    stake: float = 100
    win_probability: float | None = None


@router.post("/calculator")
def bet_calculator(req: CalcRequest):
    """Convert odds formats, calculate payouts, EV, and Kelly."""
    from sba.utils.odds_math import american_to_decimal

    # Determine base decimal odds
    if req.odds_decimal and req.odds_decimal > 1:
        dec = req.odds_decimal
    elif req.odds_american is not None:
        dec = american_to_decimal(req.odds_american)
    elif req.odds_fractional:
        parts = req.odds_fractional.replace(" ", "").split("/")
        if len(parts) == 2 and float(parts[1]) > 0:
            dec = float(parts[0]) / float(parts[1]) + 1
        else:
            dec = 2.0
    else:
        dec = 2.0

    # Convert to all formats
    if dec >= 2:
        american = round((dec - 1) * 100)
    else:
        american = round(-100 / (dec - 1))

    # Fractional
    from fractions import Fraction
    frac = Fraction(dec - 1).limit_denominator(100)
    fractional = f"{frac.numerator}/{frac.denominator}"

    implied_prob = 1 / dec
    payout = req.stake * (dec - 1)
    total_return = req.stake + payout

    # EV and Kelly if win probability given
    ev = None
    kelly = None
    if req.win_probability and 0 < req.win_probability < 1:
        ev = round(
            (req.win_probability * payout - (1 - req.win_probability) * req.stake)
            / req.stake * 100, 2
        )
        b = dec - 1
        kelly = round(
            max(0, (req.win_probability * b - (1 - req.win_probability)) / b) * 100, 2
        )

    return {
        "odds_american": american,
        "odds_decimal": round(dec, 4),
        "odds_fractional": fractional,
        "implied_probability": round(implied_prob * 100, 2),
        "stake": req.stake,
        "payout": round(payout, 2),
        "total_return": round(total_return, 2),
        "ev_pct": ev,
        "kelly_pct": kelly,
    }


class HedgeRequest(BaseModel):
    original_odds: int
    original_stake: float
    hedge_odds: int


@router.post("/calculator/hedge")
def hedge_calculator(req: HedgeRequest):
    """Calculate optimal hedge stake for guaranteed profit."""
    from sba.utils.odds_math import american_to_decimal

    orig_dec = american_to_decimal(req.original_odds)
    hedge_dec = american_to_decimal(req.hedge_odds)

    orig_return = req.original_stake * orig_dec
    # For equal profit on both sides: hedge_stake = orig_return / hedge_dec
    hedge_stake = round(orig_return / hedge_dec, 2)
    total_invested = req.original_stake + hedge_stake

    profit_if_original_wins = round(orig_return - total_invested, 2)
    profit_if_hedge_wins = round(hedge_stake * hedge_dec - total_invested, 2)
    guaranteed = round(min(profit_if_original_wins, profit_if_hedge_wins), 2)

    return {
        "hedge_stake": hedge_stake,
        "total_invested": round(total_invested, 2),
        "profit_if_original_wins": profit_if_original_wins,
        "profit_if_hedge_wins": profit_if_hedge_wins,
        "guaranteed_profit": guaranteed,
    }


# ── Data Export (JSON) ────────────────────────────────────────────

@router.get("/bets/export/json")
def export_bets_json():
    """Export bet history as JSON."""
    init_db()
    with get_connection() as conn:
        bets = repo.get_bet_history(conn)

    return [
        {
            "id": b.id,
            "date": b.placed_at.isoformat() if b.placed_at else None,
            "event_id": b.event_id,
            "market": b.market,
            "selection": b.selection,
            "line": b.line,
            "odds_american": b.odds_american,
            "odds_decimal": round(b.odds_decimal, 3),
            "stake": round(b.recommended_stake, 2),
            "bookmaker": b.bookmaker,
            "status": b.status,
            "profit_loss": round(b.profit_loss, 2),
            "model_probability": round(b.model_probability, 4),
            "expected_value": round(b.expected_value, 4),
            "kelly_fraction": round(b.kelly_fraction, 4),
        }
        for b in bets
    ]
