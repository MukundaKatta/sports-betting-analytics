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
        version="2.0.0",
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
    from sba.models.domain import TrackedBet
    from sba.utils.odds_math import american_to_decimal

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


# ── Notifications / Alerts (DB-persisted) ──────────────────────────

@router.get("/alerts")
def get_alerts():
    """Get pending edge alerts from database."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE read = 0 ORDER BY created_at DESC LIMIT 50"
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
def create_alert(alert_type: str = Query("info"), title: str = Query(...), message: str = Query("")):
    """Create a new alert."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO alerts (alert_type, title, message) VALUES (?, ?, ?)",
            (alert_type, title, message),
        )
    return {"status": "created"}


@router.delete("/alerts")
def clear_alerts():
    """Mark all alerts as read."""
    init_db()
    with get_connection() as conn:
        conn.execute("UPDATE alerts SET read = 1")
    return {"cleared": True}


@router.delete("/alerts/{alert_id}")
def dismiss_alert(alert_id: int):
    """Dismiss a single alert."""
    init_db()
    with get_connection() as conn:
        conn.execute("UPDATE alerts SET read = 1 WHERE id = ?", (alert_id,))
    return {"dismissed": True}


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


# ── Advanced Analytics Breakdowns ─────────────────────────────────

def _get_settled_bets_dicts() -> list[dict]:
    """Helper to get settled bets as dicts for analytics service."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT b.*, e.sport, e.home_team, e.away_team
            FROM bets b
            LEFT JOIN events e ON e.id = b.event_id
            WHERE b.status IN ('won', 'lost', 'push')
            ORDER BY b.placed_at
        """).fetchall()
    return [
        {
            "status": r["status"],
            "profit_loss": r["profit_loss"] or 0,
            "stake": r["recommended_stake"] or 0,
            "odds_american": r["odds_american"] or 0,
            "market": r["market"],
            "bookmaker": r["bookmaker"],
            "sport": r["sport"] if "sport" in r.keys() else "unknown",
            "placed_at": r["placed_at"],
            "selection": r["selection"],
        }
        for r in rows
    ]


def _row_to_dict(r) -> dict:
    return {
        "label": r.label, "bets": r.bets, "wins": r.wins, "losses": r.losses,
        "pushes": r.pushes, "profit": r.profit, "wagered": r.wagered,
        "win_rate": r.win_rate, "roi_pct": r.roi_pct, "avg_odds": r.avg_odds,
    }


@router.get("/analytics/by-sport")
def analytics_by_sport():
    """Performance breakdown by sport (NBA, NFL, MLB, etc.)."""
    from sba.services.analytics import breakdown_by_sport
    bets = _get_settled_bets_dicts()
    rows = breakdown_by_sport(bets)
    return {"breakdown": [_row_to_dict(r) for r in rows], "total_bets": len(bets)}


@router.get("/analytics/by-day")
def analytics_by_day_of_week():
    """Performance breakdown by day of week."""
    from sba.services.analytics import breakdown_by_day_of_week
    bets = _get_settled_bets_dicts()
    rows = breakdown_by_day_of_week(bets)
    return {"breakdown": [_row_to_dict(r) for r in rows], "total_bets": len(bets)}


@router.get("/analytics/by-odds-range")
def analytics_by_odds_range():
    """Performance breakdown by odds range bucket."""
    from sba.services.analytics import breakdown_by_odds_range
    bets = _get_settled_bets_dicts()
    rows = breakdown_by_odds_range(bets)
    return {"breakdown": [_row_to_dict(r) for r in rows], "total_bets": len(bets)}


@router.get("/analytics/by-market")
def analytics_by_market_type():
    """Performance breakdown by market type."""
    from sba.services.analytics import breakdown_by_market
    bets = _get_settled_bets_dicts()
    rows = breakdown_by_market(bets)
    return {"breakdown": [_row_to_dict(r) for r in rows], "total_bets": len(bets)}


@router.get("/analytics/by-book")
def analytics_by_bookmaker():
    """Performance breakdown by bookmaker."""
    from sba.services.analytics import breakdown_by_bookmaker
    bets = _get_settled_bets_dicts()
    rows = breakdown_by_bookmaker(bets)
    return {"breakdown": [_row_to_dict(r) for r in rows], "total_bets": len(bets)}


@router.get("/analytics/trends")
def analytics_trends(window: int = Query(7)):
    """Rolling performance trends over time."""
    from sba.services.analytics import rolling_trends
    bets = _get_settled_bets_dicts()
    points = rolling_trends(bets, window=window)
    return {
        "window": window,
        "points": [
            {"date": p.date, "profit": p.profit, "cumulative": p.cumulative,
             "win_rate": p.win_rate, "roi": p.roi, "bets": p.bets}
            for p in points
        ],
    }


@router.get("/analytics/streaks")
def analytics_streaks():
    """Detailed streak analysis with recovery metrics."""
    from sba.services.analytics import analyze_streaks
    bets = _get_settled_bets_dicts()
    s = analyze_streaks(bets)
    return {
        "current_type": s.current_type,
        "current_length": s.current_length,
        "longest_win": s.longest_win,
        "longest_loss": s.longest_loss,
        "avg_win_streak": s.avg_win_streak,
        "avg_loss_streak": s.avg_loss_streak,
        "win_streaks": s.win_streaks,
        "loss_streaks": s.loss_streaks,
        "recovery_avg": s.recovery_avg,
    }


@router.get("/analytics/heatmap")
def analytics_heatmap():
    """Day-of-week × hour performance heatmap."""
    from sba.services.analytics import performance_heatmap
    bets = _get_settled_bets_dicts()
    return {"heatmap": performance_heatmap(bets), "total_bets": len(bets)}


# ── Favorites / Watchlist (DB-persisted) ──────────────────────────

@router.get("/watchlist")
def get_watchlist():
    """Get user's watchlisted events from database."""
    init_db()
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
def add_to_watchlist(event_id: str = Query(...), label: str = Query("")):
    """Add an event to watchlist (persisted to DB)."""
    init_db()
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
def remove_from_watchlist(event_id: str):
    """Remove event from watchlist."""
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM watchlist WHERE event_id = ?", (event_id,))
        count = conn.execute("SELECT COUNT(*) as c FROM watchlist").fetchone()["c"]
    return {"status": "removed", "count": count}


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


# ── Parlay Calculator ────────────────────────────────────────────

class ParlayLeg(BaseModel):
    odds_american: int
    description: str = ""


class ParlayRequest(BaseModel):
    legs: list[ParlayLeg]
    stake: float = 100.0


@router.post("/calculator/parlay")
def parlay_calculator(req: ParlayRequest):
    """Calculate parlay odds and payout from multiple legs."""
    from sba.utils.odds_math import american_to_decimal, decimal_to_american

    if len(req.legs) < 2:
        raise HTTPException(400, "Parlay requires at least 2 legs")

    combined_decimal = 1.0
    leg_details = []
    for leg in req.legs:
        dec = american_to_decimal(leg.odds_american)
        combined_decimal *= dec
        imp_prob = 1.0 / dec
        leg_details.append({
            "description": leg.description,
            "odds_american": leg.odds_american,
            "odds_decimal": round(dec, 4),
            "implied_probability": round(imp_prob, 4),
        })

    combined_american = decimal_to_american(combined_decimal)
    payout = round(req.stake * combined_decimal, 2)
    profit = round(payout - req.stake, 2)
    combined_prob = 1.0 / combined_decimal

    return {
        "legs": leg_details,
        "num_legs": len(req.legs),
        "combined_odds_decimal": round(combined_decimal, 4),
        "combined_odds_american": combined_american,
        "combined_probability": round(combined_prob, 4),
        "stake": req.stake,
        "payout": payout,
        "profit": profit,
    }


# ── Free Bet Converter ───────────────────────────────────────────

class FreeBetRequest(BaseModel):
    free_bet_amount: float
    free_bet_odds: int
    hedge_odds: int


@router.post("/calculator/freebet")
def free_bet_converter(req: FreeBetRequest):
    """Calculate optimal hedge to convert a free bet into guaranteed cash.

    Free bets typically don't return the stake, so the profit calculation
    differs from a normal hedge.
    """
    from sba.utils.odds_math import american_to_decimal

    fb_dec = american_to_decimal(req.free_bet_odds)
    hedge_dec = american_to_decimal(req.hedge_odds)

    # Free bet profit if it wins = amount * (decimal - 1) since stake isn't returned
    fb_profit = req.free_bet_amount * (fb_dec - 1.0)

    # Hedge stake so that hedge_profit = fb_profit - hedge_stake
    # hedge_stake * hedge_dec = fb_profit  =>  hedge_stake = fb_profit / hedge_dec
    hedge_stake = fb_profit / hedge_dec
    hedge_payout = hedge_stake * hedge_dec

    # If free bet wins: profit = fb_profit - hedge_stake
    profit_if_fb_wins = round(fb_profit - hedge_stake, 2)
    # If hedge wins: profit = hedge_payout - hedge_stake (net, since free bet loses = $0)
    profit_if_hedge_wins = round(hedge_payout - hedge_stake, 2)
    guaranteed = round(min(profit_if_fb_wins, profit_if_hedge_wins), 2)
    conversion_rate = round(guaranteed / req.free_bet_amount * 100, 1)

    return {
        "free_bet_amount": req.free_bet_amount,
        "free_bet_odds": req.free_bet_odds,
        "hedge_odds": req.hedge_odds,
        "hedge_stake": round(hedge_stake, 2),
        "profit_if_free_bet_wins": profit_if_fb_wins,
        "profit_if_hedge_wins": profit_if_hedge_wins,
        "guaranteed_profit": guaranteed,
        "conversion_rate": conversion_rate,
    }


# ── No-Vig Fair Odds Calculator ──────────────────────────────────

class NoVigOutcome(BaseModel):
    name: str
    odds_american: int


class NoVigRequest(BaseModel):
    outcomes: list[NoVigOutcome]


@router.post("/calculator/novig")
def novig_calculator(req: NoVigRequest):
    """Remove vig to calculate fair/true probabilities and no-vig odds."""
    from sba.utils.odds_math import (
        american_to_decimal,
        decimal_to_american,
        decimal_to_implied_prob,
    )

    if len(req.outcomes) < 2:
        raise HTTPException(400, "Need at least 2 outcomes")

    raw = []
    for o in req.outcomes:
        dec = american_to_decimal(o.odds_american)
        imp = decimal_to_implied_prob(dec)
        raw.append({"name": o.name, "decimal": dec, "implied": imp})

    total_implied = sum(r["implied"] for r in raw)
    vig_pct = round((total_implied - 1.0) * 100, 2)

    results = []
    for r in raw:
        fair_prob = r["implied"] / total_implied
        fair_decimal = 1.0 / fair_prob if fair_prob > 0 else 0
        fair_american = decimal_to_american(fair_decimal) if fair_decimal > 1 else 0
        results.append({
            "name": r["name"],
            "original_odds": decimal_to_american(r["decimal"]),
            "original_implied_prob": round(r["implied"] * 100, 2),
            "fair_probability": round(fair_prob * 100, 2),
            "fair_odds_decimal": round(fair_decimal, 4),
            "fair_odds_american": fair_american,
        })

    return {
        "total_implied_probability": round(total_implied * 100, 2),
        "vig_percentage": vig_pct,
        "outcomes": results,
    }


# ── Arbitrage / Middles / Low-Hold Scanning ───────────────────────

@router.get("/arbitrage")
def scan_arbitrage(
    sport: str = Query("basketball_nba"),
):
    """Scan live odds for arbitrage opportunities."""
    from sba.services.arbitrage import find_arbitrage
    from sba.services.edge_finder import EdgeFinder

    settings = get_settings()
    finder = EdgeFinder(api_key=settings.odds_api_key)

    try:
        events_odds = finder.fetch_odds(sport)
    except Exception as exc:
        logger.error(f"Arb scan failed: {exc}")
        return {"opportunities": [], "error": str(exc)}

    arbs = find_arbitrage(events_odds)
    return {
        "sport": sport,
        "scanned_events": len(events_odds),
        "opportunities": [
            {
                "event": f"{a.event_away} @ {a.event_home}",
                "event_id": a.event_id,
                "market": a.market,
                "outcome_a": a.outcome_a,
                "outcome_b": a.outcome_b,
                "book_a": a.book_a,
                "book_b": a.book_b,
                "odds_a": a.odds_a_american,
                "odds_b": a.odds_b_american,
                "profit_pct": a.profit_pct,
                "stake_a_pct": a.stake_a_pct,
                "stake_b_pct": a.stake_b_pct,
            }
            for a in arbs
        ],
    }


@router.get("/middles")
def scan_middles(
    sport: str = Query("basketball_nba"),
):
    """Scan for middle betting opportunities."""
    from sba.services.arbitrage import find_middles
    from sba.services.edge_finder import EdgeFinder

    settings = get_settings()
    finder = EdgeFinder(api_key=settings.odds_api_key)

    try:
        events_odds = finder.fetch_odds(sport)
    except Exception as exc:
        logger.error(f"Middle scan failed: {exc}")
        return {"opportunities": [], "error": str(exc)}

    middles = find_middles(events_odds)
    return {
        "sport": sport,
        "scanned_events": len(events_odds),
        "opportunities": [
            {
                "event": f"{m.event_away} @ {m.event_home}",
                "event_id": m.event_id,
                "market": m.market,
                "selection": m.selection,
                "book_a": m.book_a,
                "book_b": m.book_b,
                "line_a": m.line_a,
                "line_b": m.line_b,
                "odds_a": m.odds_a_american,
                "odds_b": m.odds_b_american,
                "gap": m.gap,
                "description": m.description,
            }
            for m in middles
        ],
    }


@router.get("/low-holds")
def scan_low_holds(
    sport: str = Query("basketball_nba"),
    max_hold: float = Query(3.0, description="Max hold % to include"),
):
    """Scan for low-hold/low-vig markets."""
    from sba.services.arbitrage import find_low_holds
    from sba.services.edge_finder import EdgeFinder

    settings = get_settings()
    finder = EdgeFinder(api_key=settings.odds_api_key)

    try:
        events_odds = finder.fetch_odds(sport)
    except Exception as exc:
        logger.error(f"Low-hold scan failed: {exc}")
        return {"markets": [], "error": str(exc)}

    low_holds = find_low_holds(events_odds, max_hold=max_hold / 100.0)
    return {
        "sport": sport,
        "scanned_events": len(events_odds),
        "max_hold_pct": max_hold,
        "markets": [
            {
                "event": f"{lh.event_away} @ {lh.event_home}",
                "event_id": lh.event_id,
                "market": lh.market,
                "best_book_a": lh.best_book_a,
                "best_book_b": lh.best_book_b,
                "odds_a": lh.best_odds_a_american,
                "odds_b": lh.best_odds_b_american,
                "hold_pct": lh.hold_pct,
            }
            for lh in low_holds
        ],
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


# ── Bankroll Management ──────────────────────────────────────────

class BankrollActionRequest(BaseModel):
    amount: float
    reason: str = ""


@router.get("/bankroll")
def get_bankroll():
    """Get bankroll history and current balance."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM bankroll_log ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
    if not rows:
        settings = get_settings()
        return {
            "current_balance": settings.BANKROLL,
            "starting_balance": settings.BANKROLL,
            "total_deposited": settings.BANKROLL,
            "total_withdrawn": 0,
            "total_profit": 0,
            "roi_pct": 0,
            "history": [],
        }

    entries = [
        {
            "id": r["id"],
            "amount": r["amount"],
            "change": r["change"],
            "reason": r["reason"],
            "bet_id": r["bet_id"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    current = entries[0]["amount"]
    deposits = sum(e["change"] for e in entries if e["reason"] in ("deposit", "initial"))
    withdrawals = abs(sum(e["change"] for e in entries if e["reason"] == "withdrawal"))
    starting = entries[-1]["amount"] - entries[-1]["change"]
    total_profit = current - starting - deposits + withdrawals
    roi = round(total_profit / max(starting + deposits, 0.01) * 100, 2)

    return {
        "current_balance": round(current, 2),
        "starting_balance": round(starting, 2),
        "total_deposited": round(deposits, 2),
        "total_withdrawn": round(withdrawals, 2),
        "total_profit": round(total_profit, 2),
        "roi_pct": roi,
        "history": entries[:100],
    }


@router.post("/bankroll/deposit")
def bankroll_deposit(req: BankrollActionRequest):
    """Record a bankroll deposit."""
    init_db()
    with get_connection() as conn:
        last = conn.execute(
            "SELECT amount FROM bankroll_log ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        current = last["amount"] if last else get_settings().BANKROLL
        new_balance = current + req.amount
        conn.execute(
            "INSERT INTO bankroll_log (amount, change, reason) VALUES (?, ?, ?)",
            (round(new_balance, 2), round(req.amount, 2), req.reason or "deposit"),
        )
    return {"balance": round(new_balance, 2), "deposited": req.amount}


@router.post("/bankroll/withdraw")
def bankroll_withdraw(req: BankrollActionRequest):
    """Record a bankroll withdrawal."""
    init_db()
    with get_connection() as conn:
        last = conn.execute(
            "SELECT amount FROM bankroll_log ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        current = last["amount"] if last else get_settings().BANKROLL
        new_balance = current - req.amount
        conn.execute(
            "INSERT INTO bankroll_log (amount, change, reason) VALUES (?, ?, ?)",
            (round(new_balance, 2), round(-req.amount, 2), "withdrawal"),
        )
    return {"balance": round(new_balance, 2), "withdrawn": req.amount}


@router.post("/bankroll/initialize")
def bankroll_initialize(req: BankrollActionRequest):
    """Initialize bankroll tracking with a starting balance."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO bankroll_log (amount, change, reason) VALUES (?, ?, ?)",
            (req.amount, req.amount, "initial"),
        )
    return {"balance": req.amount, "status": "initialized"}


@router.get("/bankroll/daily")
def bankroll_daily_pnl():
    """Get daily P&L summary from bankroll log."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DATE(created_at) as day, SUM(change) as daily_change,
                   MAX(amount) as end_balance, COUNT(*) as transactions
            FROM bankroll_log
            GROUP BY DATE(created_at)
            ORDER BY day
        """).fetchall()
    return [
        {
            "date": r["day"],
            "daily_change": round(r["daily_change"], 2),
            "end_balance": round(r["end_balance"], 2),
            "transactions": r["transactions"],
        }
        for r in rows
    ]


# ── CLV Tracking (Closing Line Value) ────────────────────────────

class CLVRequest(BaseModel):
    bet_id: int
    closing_odds_american: int


@router.post("/clv/record")
def record_closing_line(req: CLVRequest):
    """Record the closing line for a bet to calculate CLV."""
    from sba.services.sharp_money import calculate_clv
    from sba.utils.odds_math import american_to_decimal

    init_db()
    with get_connection() as conn:
        bet_row = conn.execute("SELECT odds_american FROM bets WHERE id = ?", (req.bet_id,)).fetchone()
        if not bet_row:
            raise HTTPException(404, "Bet not found")

        clv = calculate_clv(bet_row["odds_american"], req.closing_odds_american)
        closing_dec = american_to_decimal(req.closing_odds_american)

        conn.execute("""
            INSERT INTO closing_lines (bet_id, closing_odds_american, closing_odds_decimal,
                                       clv_american, clv_percentage)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(bet_id) DO UPDATE SET
                closing_odds_american=excluded.closing_odds_american,
                closing_odds_decimal=excluded.closing_odds_decimal,
                clv_american=excluded.clv_american,
                clv_percentage=excluded.clv_percentage,
                captured_at=CURRENT_TIMESTAMP
        """, (req.bet_id, req.closing_odds_american, round(closing_dec, 4),
              clv["clv_american"], clv["clv_percentage"]))

    return clv


@router.get("/clv/summary")
def clv_summary():
    """Get aggregate CLV stats across all tracked bets."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT cl.*, b.market, b.bookmaker, b.status, b.odds_american as placed_odds
            FROM closing_lines cl
            JOIN bets b ON cl.bet_id = b.id
            ORDER BY cl.captured_at DESC
        """).fetchall()

    if not rows:
        return {
            "total_tracked": 0, "avg_clv": 0, "beat_closing_pct": 0,
            "clv_by_market": {}, "clv_by_bookmaker": {}, "entries": [],
        }

    entries = []
    by_market: dict[str, list] = {}
    by_book: dict[str, list] = {}

    for r in rows:
        entry = {
            "bet_id": r["bet_id"],
            "placed_odds": r["placed_odds"],
            "closing_odds": r["closing_odds_american"],
            "clv_american": r["clv_american"],
            "clv_percentage": r["clv_percentage"],
            "market": r["market"],
            "bookmaker": r["bookmaker"],
            "status": r["status"],
        }
        entries.append(entry)
        by_market.setdefault(r["market"], []).append(r["clv_percentage"])
        by_book.setdefault(r["bookmaker"], []).append(r["clv_percentage"])

    avg_clv = round(sum(r["clv_percentage"] for r in rows) / len(rows), 2)
    beat_pct = round(sum(1 for r in rows if r["clv_percentage"] > 0) / len(rows) * 100, 1)

    clv_by_market = {
        m: round(sum(vals) / len(vals), 2) for m, vals in by_market.items()
    }
    clv_by_book = {
        b: round(sum(vals) / len(vals), 2) for b, vals in by_book.items()
    }

    return {
        "total_tracked": len(rows),
        "avg_clv": avg_clv,
        "beat_closing_pct": beat_pct,
        "clv_by_market": clv_by_market,
        "clv_by_bookmaker": clv_by_book,
        "entries": entries[:50],
    }


# ── Sharp Money / Line Movement Analysis ─────────────────────────

@router.get("/sharp-money/{event_id}")
def get_sharp_signals(event_id: str, market: str = Query("h2h")):
    """Detect sharp money signals for an event from historical odds."""
    from sba.services.sharp_money import analyze_line_signals

    init_db()
    with get_connection() as conn:
        snapshots = repo.get_odds_history(conn, event_id, market)

    signals = analyze_line_signals(snapshots)
    return {
        "event_id": event_id,
        "market": market,
        "total_signals": len(signals),
        "signals": [
            {
                "outcome": s.outcome,
                "signal_type": s.signal_type,
                "bookmaker": s.bookmaker,
                "odds_open": s.odds_open,
                "odds_current": s.odds_current,
                "movement": s.movement,
                "confidence": s.confidence,
                "description": s.description,
            }
            for s in signals
        ],
    }


@router.get("/sharp-money")
def get_all_sharp_moves():
    """Get all recently detected sharp moves from the database."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT sm.*, e.home_team, e.away_team
            FROM sharp_moves sm
            LEFT JOIN events e ON sm.event_id = e.id
            ORDER BY sm.detected_at DESC LIMIT 50
        """).fetchall()
    return [
        {
            "event": f"{r['away_team'] or '?'} @ {r['home_team'] or '?'}",
            "event_id": r["event_id"],
            "market": r["market"],
            "outcome": r["outcome"],
            "move_type": r["move_type"],
            "bookmaker": r["bookmaker"],
            "odds_before": r["odds_before"],
            "odds_after": r["odds_after"],
            "line_before": r["line_before"],
            "line_after": r["line_after"],
            "magnitude": r["magnitude"],
            "detected_at": r["detected_at"],
        }
        for r in rows
    ]


# ── Community / Leaderboard ──────────────────────────────────────

class RegisterUserRequest(BaseModel):
    username: str
    display_name: str = ""


class SubmitPickRequest(BaseModel):
    username: str
    event_id: str
    market: str
    selection: str
    odds_american: int
    line: float | None = None
    confidence: str = "medium"
    analysis: str = ""


class SettlePickRequest(BaseModel):
    status: str
    profit_loss: float = 0.0


@router.get("/leaderboard")
def get_leaderboard(limit: int = Query(25)):
    """Get the community leaderboard ranked by score."""
    init_db()
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
def register_user(req: RegisterUserRequest):
    """Register a new user for the leaderboard."""
    init_db()
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


@router.post("/picks")
def submit_pick(req: SubmitPickRequest):
    """Submit a public pick."""
    init_db()
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
def settle_pick(pick_id: int, req: SettlePickRequest):
    """Settle a public pick and update the leaderboard."""
    if req.status not in ("won", "lost", "push"):
        raise HTTPException(400, "Status must be 'won', 'lost', or 'push'")

    init_db()
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
def get_picks(username: str = Query(None), limit: int = Query(50)):
    """Get public picks, optionally filtered by username."""
    init_db()
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


# ── Alert Rules (Automated Alerts) ───────────────────────────────

class CreateAlertRuleRequest(BaseModel):
    rule_type: str  # ev_threshold, arb_detected, line_movement, price_change
    condition_json: str = "{}"


@router.get("/alert-rules")
def get_alert_rules():
    """Get all configured alert rules."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM alert_rules ORDER BY created_at DESC"
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
def create_alert_rule(req: CreateAlertRuleRequest):
    """Create a new alert rule."""
    valid_types = {"ev_threshold", "arb_detected", "line_movement", "price_change"}
    if req.rule_type not in valid_types:
        raise HTTPException(400, f"rule_type must be one of: {valid_types}")

    init_db()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO alert_rules (rule_type, condition_json) VALUES (?, ?)",
            (req.rule_type, req.condition_json),
        )
    return {"id": cursor.lastrowid, "status": "created"}


@router.put("/alert-rules/{rule_id}/toggle")
def toggle_alert_rule(rule_id: int):
    """Toggle an alert rule on/off."""
    init_db()
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
def delete_alert_rule(rule_id: int):
    """Delete an alert rule."""
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
    return {"id": rule_id, "deleted": True}


# ── Bet Tags & Notes ─────────────────────────────────────────────

class AddTagRequest(BaseModel):
    tag: str


class AddNoteRequest(BaseModel):
    note: str


@router.post("/bets/{bet_id}/tags")
def add_bet_tag(bet_id: int, req: AddTagRequest):
    """Add a tag to a bet."""
    init_db()
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO bet_tags (bet_id, tag) VALUES (?, ?)",
                (bet_id, req.tag),
            )
        except Exception:
            return {"status": "already_exists"}
    return {"bet_id": bet_id, "tag": req.tag, "status": "added"}


@router.get("/bets/{bet_id}/tags")
def get_bet_tags(bet_id: int):
    """Get all tags for a bet."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tag FROM bet_tags WHERE bet_id = ?", (bet_id,)
        ).fetchall()
    return [r["tag"] for r in rows]


@router.delete("/bets/{bet_id}/tags/{tag}")
def remove_bet_tag(bet_id: int, tag: str):
    """Remove a tag from a bet."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM bet_tags WHERE bet_id = ? AND tag = ?", (bet_id, tag),
        )
    return {"bet_id": bet_id, "tag": tag, "status": "removed"}


@router.post("/bets/{bet_id}/notes")
def add_bet_note(bet_id: int, req: AddNoteRequest):
    """Add a note to a bet."""
    init_db()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO bet_notes (bet_id, note) VALUES (?, ?)",
            (bet_id, req.note),
        )
    return {"id": cursor.lastrowid, "bet_id": bet_id, "status": "added"}


@router.get("/bets/{bet_id}/notes")
def get_bet_notes(bet_id: int):
    """Get all notes for a bet."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM bet_notes WHERE bet_id = ? ORDER BY created_at DESC",
            (bet_id,),
        ).fetchall()
    return [
        {"id": r["id"], "note": r["note"], "created_at": r["created_at"]}
        for r in rows
    ]


# ── Same-Game Parlay / Correlation Builder ───────────────────────

class SGPLegRequest(BaseModel):
    market: str
    selection: str
    direction: str  # over, under, cover, yes, no
    odds_american: int
    player_name: str = ""


class SGPRequest(BaseModel):
    legs: list[SGPLegRequest]
    stake: float = 100.0


@router.post("/calculator/sgp")
def sgp_builder(req: SGPRequest):
    """Build a same-game parlay with correlation adjustments.

    Unlike naive parlay calculators, this accounts for statistical
    correlations between markets (e.g., points & threes are correlated).
    """
    from sba.services.correlations import SGPLeg, build_sgp
    from sba.utils.odds_math import american_to_decimal, decimal_to_implied_prob

    if len(req.legs) < 2:
        raise HTTPException(400, "SGP requires at least 2 legs")

    legs = []
    for leg in req.legs:
        dec = american_to_decimal(leg.odds_american)
        imp = decimal_to_implied_prob(dec)
        legs.append(SGPLeg(
            market=leg.market,
            selection=leg.selection,
            direction=leg.direction,
            odds_american=leg.odds_american,
            odds_decimal=round(dec, 4),
            implied_prob=round(imp, 4),
            player_name=leg.player_name,
        ))

    analysis = build_sgp(legs)

    payout = round(req.stake * analysis.correlated_odds_decimal, 2)
    profit = round(payout - req.stake, 2)

    return {
        "num_legs": len(legs),
        "naive_odds_american": analysis.naive_odds_american,
        "naive_odds_decimal": analysis.naive_odds_decimal,
        "correlated_odds_american": analysis.correlated_odds_american,
        "correlated_odds_decimal": analysis.correlated_odds_decimal,
        "naive_probability": round(analysis.naive_probability * 100, 3),
        "correlated_probability": round(analysis.correlated_probability * 100, 3),
        "correlation_adjustment_pct": analysis.correlation_adjustment,
        "correlations": analysis.correlations,
        "stake": req.stake,
        "payout": payout,
        "profit": profit,
        "legs": [
            {
                "player": l.player_name,
                "market": l.market,
                "direction": l.direction,
                "odds_american": l.odds_american,
                "implied_prob": round(l.implied_prob * 100, 1),
            }
            for l in legs
        ],
    }


@router.get("/correlations")
def get_correlation_matrix():
    """Get the known correlation matrix for SGP pricing."""
    from sba.services.correlations import CORRELATION_MATRIX

    return [
        {
            "market_a": k[0],
            "direction_a": k[1],
            "market_b": k[2],
            "direction_b": k[3],
            "correlation": v,
        }
        for k, v in CORRELATION_MATRIX.items()
        if v != 0
    ]


# ── Power Ratings ────────────────────────────────────────────────

@router.get("/power-ratings")
def get_power_ratings(sport: str = Query("basketball_nba")):
    """Get team power ratings derived from market odds."""
    from sba.services.power_ratings import calculate_ratings_from_odds

    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT e.home_team, e.away_team, e.sport,
                   os_h.price_american as home_odds,
                   os_a.price_american as away_odds
            FROM events e
            JOIN odds_snapshots os_h ON os_h.event_id = e.id
                AND os_h.market = 'h2h' AND os_h.outcome_name = e.home_team
            JOIN odds_snapshots os_a ON os_a.event_id = e.id
                AND os_a.market = 'h2h' AND os_a.outcome_name = e.away_team
                AND os_a.bookmaker = os_h.bookmaker
            WHERE e.sport LIKE ?
            ORDER BY os_h.snapshot_time DESC
            LIMIT 200
        """, (f"%{sport.split('_')[-1]}%",)).fetchall()

    events = [
        {
            "home_team": r["home_team"],
            "away_team": r["away_team"],
            "sport": r["sport"],
            "home_odds_american": r["home_odds"],
            "away_odds_american": r["away_odds"],
        }
        for r in rows
    ]

    ratings = calculate_ratings_from_odds(events)
    return {
        "sport": sport,
        "teams_rated": len(ratings),
        "ratings": [
            {
                "rank": r.rank,
                "team": r.team,
                "rating": r.rating,
                "win_pct": round(r.implied_win_pct * 100, 1),
                "games_rated": r.games_rated,
                "trend": r.trend,
            }
            for r in ratings
        ],
    }


@router.get("/matchup")
def analyze_matchup_endpoint(
    home: str = Query(...),
    away: str = Query(...),
    sport: str = Query("basketball_nba"),
    spread: float = Query(None),
):
    """Analyze a head-to-head matchup using power ratings."""
    from sba.services.power_ratings import analyze_matchup, calculate_ratings_from_odds

    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT e.home_team, e.away_team, e.sport,
                   os_h.price_american as home_odds,
                   os_a.price_american as away_odds
            FROM events e
            JOIN odds_snapshots os_h ON os_h.event_id = e.id
                AND os_h.market = 'h2h' AND os_h.outcome_name = e.home_team
            JOIN odds_snapshots os_a ON os_a.event_id = e.id
                AND os_a.market = 'h2h' AND os_a.outcome_name = e.away_team
                AND os_a.bookmaker = os_h.bookmaker
            ORDER BY os_h.snapshot_time DESC LIMIT 200
        """).fetchall()

    events = [
        {
            "home_team": r["home_team"], "away_team": r["away_team"],
            "sport": r["sport"],
            "home_odds_american": r["home_odds"],
            "away_odds_american": r["away_odds"],
        }
        for r in rows
    ]
    ratings = calculate_ratings_from_odds(events)
    analysis = analyze_matchup(home, away, ratings, market_spread=spread)

    return {
        "home_team": analysis.home_team,
        "away_team": analysis.away_team,
        "home_rating": analysis.home_rating,
        "away_rating": analysis.away_rating,
        "home_win_prob": round(analysis.home_win_prob * 100, 1),
        "away_win_prob": round(analysis.away_win_prob * 100, 1),
        "predicted_spread": analysis.predicted_spread,
        "rating_diff": analysis.rating_diff,
        "home_edge": analysis.home_edge,
        "away_edge": analysis.away_edge,
    }


# ── Promo / Bonus Optimizer ──────────────────────────────────────

class PromoRequest(BaseModel):
    promo_type: str  # risk_free, deposit_match, profit_boost, free_bet
    amount: float
    rollover: float = 1.0  # Rollover requirement multiplier
    min_odds: int = -200  # Minimum odds requirement


@router.post("/calculator/promo")
def promo_optimizer(req: PromoRequest):
    """Calculate optimal strategy for sportsbook promotions.

    Handles risk-free bets, deposit matches, profit boosts, and free bets.
    """
    from sba.utils.odds_math import american_to_decimal

    if req.promo_type == "risk_free":
        # Risk-free: if you lose, get the stake back as free bet
        # Best strategy: bet on a heavy favorite, then convert free bet
        # Expected conversion: ~70% on risk-free, ~65-70% free bet portion
        expected_value = round(req.amount * 0.70, 2)
        strategy = (
            "Place on slight underdog (+200 to +300). If it loses, "
            "convert the free bet using the Free Bet Converter at ~65-70% rate."
        )
        optimal_odds = "+250"

    elif req.promo_type == "deposit_match":
        # Deposit match: play through rollover, minimize expected loss
        min_dec = american_to_decimal(req.min_odds)
        implied_hold = 1.0 - (1.0 / min_dec)  # Approximate house edge
        play_through = req.amount * req.rollover
        expected_loss = round(play_through * 0.02, 2)  # ~2% house edge on low-hold
        expected_value = round(req.amount - expected_loss, 2)
        strategy = (
            f"Bet ${play_through:.0f} total on low-hold markets (≤2% vig). "
            f"Expected loss: ${expected_loss}. Net value: ${expected_value}."
        )
        optimal_odds = "-110 / -110 (low hold)"

    elif req.promo_type == "profit_boost":
        # Profit boost: increased odds on a bet
        boosted_value = round(req.amount * 0.05 * req.rollover, 2)  # ~5% boost value
        expected_value = round(boosted_value, 2)
        strategy = (
            "Use on a bet you'd make anyway. The boost adds ~5% to your EV. "
            "Best used on heavy underdogs to maximize the dollar value of the boost."
        )
        optimal_odds = "+300 or longer"

    elif req.promo_type == "free_bet":
        # Same as free bet converter - ~65-70% conversion
        expected_value = round(req.amount * 0.70, 2)
        strategy = (
            "Use the Free Bet Converter. Place the free bet on a long underdog "
            "(+300 to +500) and hedge on a different book for ~70% conversion."
        )
        optimal_odds = "+400 free bet, hedge at -400"

    else:
        raise HTTPException(400, f"Unknown promo type: {req.promo_type}")

    return {
        "promo_type": req.promo_type,
        "amount": req.amount,
        "rollover": req.rollover,
        "expected_value": expected_value,
        "strategy": strategy,
        "optimal_odds": optimal_odds,
        "conversion_rate": round(expected_value / req.amount * 100, 1),
    }


# ── Odds Screen (Real-time Odds Dashboard) ───────────────────────

@router.get("/odds-screen")
def odds_screen(
    sport: str = Query("basketball_nba"),
    market: str = Query("h2h"),
):
    """Get a comprehensive odds screen showing all events with best odds.

    Like OddsJam's main screen: every game, every book, best price highlighted.
    """
    init_db()
    with get_connection() as conn:
        # Get all upcoming events
        events = conn.execute("""
            SELECT * FROM events WHERE completed = 0
            ORDER BY commence_time LIMIT 50
        """).fetchall()

        odds_screen_data = []
        for event in events:
            # Get latest odds for each bookmaker
            snapshots = conn.execute("""
                SELECT bookmaker, outcome_name, outcome_point,
                       price_american, price_decimal,
                       MAX(snapshot_time) as latest_time
                FROM odds_snapshots
                WHERE event_id = ? AND market = ?
                GROUP BY bookmaker, outcome_name
                ORDER BY bookmaker
            """, (event["id"], market)).fetchall()

            if not snapshots:
                continue

            # Organize by outcome
            by_outcome: dict[str, list] = {}
            for s in snapshots:
                outcome = s["outcome_name"]
                by_outcome.setdefault(outcome, []).append({
                    "bookmaker": s["bookmaker"],
                    "odds_american": s["price_american"],
                    "odds_decimal": round(s["price_decimal"], 3),
                    "line": s["outcome_point"],
                })

            # Find best odds for each outcome
            best_odds = {}
            for outcome, books in by_outcome.items():
                best = max(books, key=lambda b: b["odds_decimal"])
                best_odds[outcome] = {
                    "bookmaker": best["bookmaker"],
                    "odds_american": best["odds_american"],
                }

            odds_screen_data.append({
                "event_id": event["id"],
                "home_team": event["home_team"],
                "away_team": event["away_team"],
                "commence_time": event["commence_time"],
                "sport": event["sport"],
                "market": market,
                "outcomes": by_outcome,
                "best_odds": best_odds,
                "num_books": len({s["bookmaker"] for s in snapshots}),
            })

    return {
        "sport": sport,
        "market": market,
        "events": odds_screen_data,
        "total_events": len(odds_screen_data),
    }


# ── Consensus / Expected Value Screen ────────────────────────────

@router.get("/consensus/{event_id}")
def get_consensus(event_id: str):
    """Get consensus odds and implied probabilities across all books.

    Like BettingPros' consensus feature - aggregates all bookmaker opinions.
    """
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT bookmaker, market, outcome_name, outcome_point,
                   price_american, price_decimal,
                   MAX(snapshot_time) as latest
            FROM odds_snapshots
            WHERE event_id = ?
            GROUP BY bookmaker, market, outcome_name
            ORDER BY market, outcome_name, bookmaker
        """, (event_id,)).fetchall()

    if not rows:
        return {"event_id": event_id, "markets": {}}

    from sba.utils.odds_math import decimal_to_implied_prob

    markets: dict[str, dict] = {}
    for r in rows:
        mkt = r["market"]
        outcome = r["outcome_name"]
        if mkt not in markets:
            markets[mkt] = {}
        if outcome not in markets[mkt]:
            markets[mkt][outcome] = {"books": [], "line": r["outcome_point"]}

        dec = r["price_decimal"]
        imp = decimal_to_implied_prob(dec)

        markets[mkt][outcome]["books"].append({
            "bookmaker": r["bookmaker"],
            "odds_american": r["price_american"],
            "odds_decimal": round(dec, 3),
            "implied_prob": round(imp, 4),
        })

    # Calculate consensus for each outcome
    for mkt in markets:
        for outcome in markets[mkt]:
            books = markets[mkt][outcome]["books"]
            if books:
                avg_prob = sum(b["implied_prob"] for b in books) / len(books)
                best = max(books, key=lambda b: b["odds_decimal"])
                worst = min(books, key=lambda b: b["odds_decimal"])

                markets[mkt][outcome]["consensus_prob"] = round(avg_prob, 4)
                markets[mkt][outcome]["best_odds"] = best["odds_american"]
                markets[mkt][outcome]["best_book"] = best["bookmaker"]
                markets[mkt][outcome]["worst_odds"] = worst["odds_american"]
                markets[mkt][outcome]["num_books"] = len(books)
                markets[mkt][outcome]["spread"] = best["odds_american"] - worst["odds_american"]

    return {"event_id": event_id, "markets": markets}


# ── Multi-Sport Support ──────────────────────────────────────────

@router.get("/sports")
def get_available_sports():
    """Get all available sports with event counts."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT sport, COUNT(*) as event_count,
                   SUM(CASE WHEN completed = 0 THEN 1 ELSE 0 END) as upcoming
            FROM events
            GROUP BY sport
            ORDER BY event_count DESC
        """).fetchall()

    sports = [
        {
            "key": r["sport"],
            "name": r["sport"].replace("_", " ").title(),
            "event_count": r["event_count"],
            "upcoming": r["upcoming"],
        }
        for r in rows
    ]

    # Add known sports that might not have data yet
    known_sports = [
        {"key": "basketball_nba", "name": "NBA"},
        {"key": "basketball_ncaab", "name": "NCAAB"},
        {"key": "americanfootball_nfl", "name": "NFL"},
        {"key": "baseball_mlb", "name": "MLB"},
        {"key": "icehockey_nhl", "name": "NHL"},
        {"key": "soccer_epl", "name": "EPL Soccer"},
        {"key": "soccer_usa_mls", "name": "MLS"},
        {"key": "mma_mixed_martial_arts", "name": "UFC/MMA"},
        {"key": "tennis_atp", "name": "ATP Tennis"},
    ]

    existing_keys = {s["key"] for s in sports}
    for ks in known_sports:
        if ks["key"] not in existing_keys:
            sports.append({**ks, "event_count": 0, "upcoming": 0})

    return sports


# ── Multi-Method Devig Engine (Outlier Pro) ─────────────────────

class DevigRequest(BaseModel):
    odds_american: list[int]
    outcome_names: list[str] | None = None
    method: str = "multiplicative"


class MultiDevigRequest(BaseModel):
    book_odds: list[dict]  # [{"bookmaker": str, "odds": [int, ...]}]
    outcome_names: list[str] | None = None
    methods: list[str] | None = None
    method_weights: dict[str, float] | None = None


@router.post("/calculator/devig")
def devig_calculator(req: DevigRequest):
    """Devig odds using a single method."""
    from sba.services.devig import devig_single

    result = devig_single(
        req.odds_american,
        method=req.method,
        outcome_names=req.outcome_names,
    )
    return {
        "method": result.method,
        "outcomes": [
            {
                "name": name,
                "fair_prob": round(prob * 100, 2),
                "fair_american": am,
                "fair_decimal": dec,
            }
            for name, prob, am, dec in zip(
                result.outcome_names,
                result.fair_probabilities,
                result.fair_odds_american,
                result.fair_odds_decimal,
            )
        ],
        "vig_removed": result.vig_removed,
    }


@router.post("/calculator/devig/multi")
def multi_devig_calculator(req: MultiDevigRequest):
    """Multi-book, multi-method devigging like Outlier Pro."""
    from sba.services.devig import devig_multi

    result = devig_multi(
        req.book_odds,
        methods=req.methods,
        method_weights=req.method_weights,
        outcome_names=req.outcome_names,
    )
    return {
        "outcomes": result.outcomes,
        "books_used": result.books_used,
        "consensus_vig": result.consensus_vig,
        "best_method": result.best_method,
        "weighted_consensus": [
            {
                "name": name,
                "fair_prob": round(prob * 100, 2),
                "fair_american": am,
                "fair_decimal": dec,
            }
            for name, prob, am, dec in zip(
                result.outcomes,
                result.weighted_fair_probs,
                result.weighted_fair_american,
                result.weighted_fair_decimal,
            )
        ],
        "methods": [
            {
                "method": m.method,
                "outcomes": [
                    {
                        "name": name,
                        "fair_prob": round(p * 100, 2),
                        "fair_american": am,
                    }
                    for name, p, am in zip(
                        m.outcome_names, m.fair_probabilities, m.fair_odds_american
                    )
                ],
                "vig_removed": m.vig_removed,
            }
            for m in result.methods
        ],
    }


# ── Bet Grading System (BetQL 1-5 Stars) ────────────────────────

class GradeBetRequest(BaseModel):
    selection: str
    market: str
    event: str
    edge_pct: float
    best_odds_american: int
    fair_odds_american: int | None = None
    sharp_book_agrees: bool = False
    line_moving_toward: bool = False
    line_moving_away: bool = False
    historical_hit_rate: float | None = None
    books_with_edge: int = 1
    total_books: int = 1
    is_live: bool = False
    hours_to_start: float | None = None


@router.post("/bet-grade")
def grade_bet_endpoint(req: GradeBetRequest):
    """Grade a bet opportunity with 1-5 star rating like BetQL."""
    from sba.services.bet_grader import grade_bet

    grade = grade_bet(
        selection=req.selection,
        market=req.market,
        event=req.event,
        edge_pct=req.edge_pct,
        best_odds_american=req.best_odds_american,
        fair_odds_american=req.fair_odds_american,
        sharp_book_agrees=req.sharp_book_agrees,
        line_moving_toward=req.line_moving_toward,
        line_moving_away=req.line_moving_away,
        historical_hit_rate=req.historical_hit_rate,
        books_with_edge=req.books_with_edge,
        total_books=req.total_books,
        is_live=req.is_live,
        hours_to_start=req.hours_to_start,
    )
    return {
        "selection": grade.selection,
        "market": grade.market,
        "event": grade.event,
        "stars": grade.stars,
        "overall_score": grade.overall_score,
        "edge_pct": grade.edge_pct,
        "confidence": grade.confidence,
        "grade_label": grade.grade_label,
        "components": {
            "edge": grade.edge_score,
            "sharp_agreement": grade.sharp_score,
            "line_movement": grade.movement_score,
            "consistency": grade.consistency_score,
            "market_efficiency": grade.market_score,
        },
        "reasons": grade.reasons,
        "warnings": grade.warnings,
    }


@router.get("/bet-grades")
def get_graded_edges():
    """Get all current edges with star ratings applied."""
    from sba.services.bet_grader import grade_bet

    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT e.home_team, e.away_team, e.id as event_id,
                   os.market, os.outcome_name, os.price_american,
                   os.price_decimal, os.bookmaker
            FROM events e
            JOIN odds_snapshots os ON os.event_id = e.id
            WHERE e.completed = 0
            ORDER BY os.snapshot_time DESC
            LIMIT 100
        """).fetchall()

    if not rows:
        return {"grades": [], "total": 0}

    # Simple grading based on available data
    grades = []
    for r in rows:
        edge = max(0, (1.0 / r["price_decimal"] - 0.5) * 100) if r["price_decimal"] > 0 else 0
        if edge < 1:
            continue
        g = grade_bet(
            selection=r["outcome_name"],
            market=r["market"],
            event=f"{r['home_team']} vs {r['away_team']}",
            edge_pct=round(edge, 1),
            best_odds_american=r["price_american"],
        )
        grades.append({
            "selection": g.selection,
            "event": g.event,
            "market": g.market,
            "stars": g.stars,
            "score": g.overall_score,
            "edge_pct": g.edge_pct,
            "odds_american": r["price_american"],
            "bookmaker": r["bookmaker"],
            "confidence": g.confidence,
            "grade_label": g.grade_label,
            "reasons": g.reasons,
        })

    grades.sort(key=lambda x: x["score"], reverse=True)
    return {"grades": grades[:50], "total": len(grades)}


# ── Backtesting Engine (Rithmm) ──────────────────────────────────

class BacktestRequest(BaseModel):
    strategy_name: str = "Custom Strategy"
    starting_bankroll: float = 10000.0
    stake_type: str = "flat"
    stake_amount: float = 100.0
    min_edge: float = 0.0
    min_odds: int = -500
    max_odds: int = 5000
    stop_loss: float | None = None
    take_profit: float | None = None


@router.post("/backtest")
def run_backtest_endpoint(req: BacktestRequest):
    """Backtest a strategy against historical bet data."""
    from sba.services.backtester import run_backtest

    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT b.event_id, b.selection, b.odds_american,
                   b.odds_decimal, b.status, b.profit_loss
            FROM bets b
            WHERE b.status IN ('won', 'lost', 'push', 'win', 'loss')
            ORDER BY b.placed_at
        """).fetchall()

    historical = [
        {
            "event": r["event_id"] or "",
            "selection": r["selection"] or "",
            "odds_american": r["odds_american"] or -110,
            "odds_decimal": r["odds_decimal"] or 1.909,
            "result": "win" if r["status"] in ("won", "win") else "push" if r["status"] == "push" else "loss",
        }
        for r in rows
    ]

    if not historical:
        # Generate sample data for demonstration
        import random
        random.seed(42)
        historical = []
        for i in range(200):
            odds = random.choice([-110, -115, 100, 120, 150, -130, -105, 200])
            dec = 1 + (odds / 100) if odds > 0 else 1 + (100 / abs(odds))
            imp = 1 / dec
            # Simulate with slight edge
            win_chance = imp + 0.02
            result = "win" if random.random() < win_chance else "loss"
            historical.append({
                "event": f"Game_{i+1}",
                "selection": f"Team_{random.choice(['A','B'])}",
                "odds_american": odds,
                "odds_decimal": round(dec, 3),
                "result": result,
                "edge_pct": round(random.uniform(0, 8), 1),
            })

    bt = run_backtest(
        historical,
        strategy_name=req.strategy_name,
        starting_bankroll=req.starting_bankroll,
        stake_type=req.stake_type,
        stake_amount=req.stake_amount,
        min_edge=req.min_edge,
        min_odds=req.min_odds,
        max_odds=req.max_odds,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
    )

    return {
        "strategy_name": bt.strategy_name,
        "grade": bt.grade,
        "total_bets": bt.total_bets,
        "wins": bt.wins,
        "losses": bt.losses,
        "pushes": bt.pushes,
        "win_rate": bt.win_rate,
        "total_wagered": bt.total_wagered,
        "total_profit": bt.total_profit,
        "roi_pct": bt.roi_pct,
        "max_drawdown": bt.max_drawdown,
        "max_drawdown_pct": bt.max_drawdown_pct,
        "sharpe_ratio": bt.sharpe_ratio,
        "longest_win_streak": bt.longest_win_streak,
        "longest_lose_streak": bt.longest_lose_streak,
        "avg_odds": bt.avg_odds,
        "avg_stake": bt.avg_stake,
        "profit_factor": bt.profit_factor,
        "starting_bankroll": bt.starting_bankroll,
        "ending_bankroll": bt.ending_bankroll,
        "peak_bankroll": bt.peak_bankroll,
        "equity_curve": bt.equity_curve,
    }


# ── Public Money / Sharp vs Public (Action Network) ─────────────

@router.get("/public-money/{event_id}")
def get_public_money(event_id: str, market: str = Query("h2h")):
    """Get public bet % vs money % for an event like Action Network."""
    from sba.services.public_money import simulate_public_money

    init_db()
    with get_connection() as conn:
        event = conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()

        if not event:
            raise HTTPException(404, "Event not found")

        # Get latest odds for simulation
        odds = conn.execute("""
            SELECT outcome_name, price_american
            FROM odds_snapshots
            WHERE event_id = ? AND market = ?
            ORDER BY snapshot_time DESC LIMIT 2
        """, (event_id, market)).fetchall()

    if len(odds) >= 2:
        home_odds = odds[0]["price_american"]
        away_odds = odds[1]["price_american"]
    else:
        home_odds = -110
        away_odds = -110

    analysis = simulate_public_money(
        event_id=event_id,
        home_team=event["home_team"],
        away_team=event["away_team"],
        home_odds_american=home_odds,
        away_odds_american=away_odds,
        market=market,
    )

    return {
        "event_id": analysis.event_id,
        "market": analysis.market,
        "sharp_signal": analysis.sharp_signal,
        "signal_strength": analysis.signal_strength,
        "description": analysis.description,
        "outcomes": [
            {
                "name": o.outcome,
                "bet_pct": o.bet_pct,
                "money_pct": o.money_pct,
                "divergence": o.divergence,
                "sharp_side": o.sharp_side,
            }
            for o in analysis.outcomes
        ],
    }


@router.post("/public-money/analyze")
def analyze_public_money_endpoint(
    event_id: str = Query(...),
    market: str = Query("h2h"),
    outcomes: list[dict] = [],
):
    """Analyze custom public money data."""
    from sba.services.public_money import analyze_public_money

    analysis = analyze_public_money(event_id, market, outcomes)
    return {
        "event_id": analysis.event_id,
        "market": analysis.market,
        "sharp_signal": analysis.sharp_signal,
        "signal_strength": analysis.signal_strength,
        "description": analysis.description,
        "outcomes": [
            {
                "name": o.outcome,
                "bet_pct": o.bet_pct,
                "money_pct": o.money_pct,
                "divergence": o.divergence,
                "sharp_side": o.sharp_side,
            }
            for o in analysis.outcomes
        ],
    }
