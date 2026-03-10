"""Performance today, equity curve, bet grades, insights, achievements, CLV,
power ratings, sharp/public money, correlations, staking, simulate, backtest endpoints."""

from __future__ import annotations

import logging
import random

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from sba.config import get_settings
from sba.data.db import get_connection
from sba.web.api import repo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["performance"])


# ── Pydantic models ─────────────────────────────────────────────────

class SimulationRequest(BaseModel):
    bankroll: float = 1000
    num_bets: int = 100
    avg_odds: int = -110
    win_rate: float = 0.53
    kelly_fraction: float = 0.25
    simulations: int = 50


class CLVRequest(BaseModel):
    bet_id: int
    closing_odds_american: int


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


class BetRatingRequest(BaseModel):
    odds_american: int
    model_probability: float | None = None
    ev_pct: float | None = None
    kelly_fraction: float | None = None
    clv: float | None = None


class StakingRequest(BaseModel):
    bankroll: float
    odds_decimal: float = 2.0
    win_probability: float = 0.55
    ev_pct: float = 5.0
    confidence: str = "medium"
    loss_streak: int = 0


# ── Helpers ──────────────────────────────────────────────────────────

def _get_settled_bets_dicts() -> list[dict]:
    """Helper to get settled bets as dicts for analytics service."""
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


def _get_user_stats() -> dict:
    """Gather user stats for achievement evaluation."""
    with get_connection() as conn:
        bets = conn.execute(
            "SELECT * FROM bets WHERE status IN ('won','lost','push')"
        ).fetchall()
        picks = conn.execute("SELECT COUNT(*) as cnt FROM public_picks").fetchone()

    total = len(bets)
    won = sum(1 for b in bets if b["status"] == "won")
    lost = sum(1 for b in bets if b["status"] == "lost")
    profit = sum((b["profit_loss"] or 0) for b in bets)
    staked = sum(abs(b["recommended_stake"] or 0) for b in bets) or 1
    roi = profit / staked * 100 if staked > 0 else 0

    sports = set()
    books = set()
    for b in bets:
        if b["bookmaker"]:
            books.add(b["bookmaker"])
    with get_connection() as conn:
        sport_rows = conn.execute("""
            SELECT DISTINCT e.sport FROM bets b
            JOIN events e ON e.id = b.event_id
            WHERE b.status IN ('won','lost','push') AND e.sport IS NOT NULL
        """).fetchall()
    sports = {r["sport"] for r in sport_rows}

    # Longest win streak
    longest_win = 0
    current_win = 0
    biggest_dog = 0
    for b in bets:
        if b["status"] == "won":
            current_win += 1
            longest_win = max(longest_win, current_win)
            odds = b["odds_american"] or 0
            if odds > 0:
                biggest_dog = max(biggest_dog, odds)
        else:
            current_win = 0

    return {
        "total_bets": total,
        "wins": won,
        "losses": lost,
        "total_profit": profit,
        "roi_pct": round(roi, 1),
        "longest_win_streak": longest_win,
        "unique_sports": len(sports),
        "unique_books": len(books),
        "total_picks": picks["cnt"] if picks else 0,
        "biggest_underdog_win": biggest_dog,
        "analytics_views": 0,
        "perfect_weeks": 0,
        "comeback_count": 0,
    }


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/simulate")
def run_simulation(req: SimulationRequest):
    """Run Monte Carlo bankroll simulation."""
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


# ── CLV Tracking ─────────────────────────────────────────────────────

@router.post("/clv/record")
def record_closing_line(req: CLVRequest):
    """Record the closing line for a bet to calculate CLV."""
    from sba.services.sharp_money import calculate_clv
    from sba.utils.odds_math import american_to_decimal

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


# ── Sharp Money / Line Movement Analysis ─────────────────────────────

@router.get("/sharp-money/{event_id}")
def get_sharp_signals(event_id: str, market: str = Query("h2h")):
    """Detect sharp money signals for an event from historical odds."""
    from sba.services.sharp_money import analyze_line_signals

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


# ── Power Ratings ─────────────────────────────────────────────────────

@router.get("/power-ratings")
def get_power_ratings(sport: str = Query("basketball_nba")):
    """Get team power ratings derived from market odds."""
    from sba.services.power_ratings import calculate_ratings_from_odds

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


# ── Public Money ──────────────────────────────────────────────────────

@router.get("/public-money/{event_id}")
def get_public_money(event_id: str, market: str = Query("h2h")):
    """Get public bet % vs money % for an event like Action Network."""
    from sba.services.public_money import simulate_public_money

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


# ── Correlations ─────────────────────────────────────────────────────

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


# ── Bet Grading ──────────────────────────────────────────────────────

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


# ── Backtest ──────────────────────────────────────────────────────────

@router.post("/backtest")
def run_backtest_endpoint(req: BacktestRequest):
    """Backtest a strategy against historical bet data."""
    from sba.services.backtester import run_backtest

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


# ── Achievements ──────────────────────────────────────────────────────

@router.get("/achievements")
def get_achievements():
    """Get all achievements with unlock status and progress."""
    from sba.services.achievements import evaluate_achievements, get_achievement_summary

    stats = _get_user_stats()
    achievements = evaluate_achievements(stats)
    summary = get_achievement_summary(achievements)

    return {
        "achievements": achievements,
        "summary": summary,
        "stats": stats,
    }


@router.get("/achievements/summary")
def get_achievements_summary():
    """Quick summary of achievement progress for dashboard widget."""
    from sba.services.achievements import evaluate_achievements, get_achievement_summary

    stats = _get_user_stats()
    achievements = evaluate_achievements(stats)
    summary = get_achievement_summary(achievements)
    recent_unlocked = [a for a in achievements if a["unlocked"]][-3:]

    return {
        "total_unlocked": summary["total_unlocked"],
        "total_achievements": summary["total_achievements"],
        "total_points": summary["total_points"],
        "rank": summary["rank"],
        "recent_unlocked": recent_unlocked,
        "next_unlock": summary["next_unlock"],
    }


# ── Insights ──────────────────────────────────────────────────────────

@router.get("/insights")
def get_insights():
    """Get personalized AI-powered insights and recommendations."""
    from sba.services.insights import generate_insights

    bets = _get_settled_bets_dicts()

    # Get bankroll
    bankroll = 0
    with get_connection() as conn:
        row = conn.execute(
            "SELECT amount FROM bankroll_log ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            bankroll = row["amount"]

    insights = generate_insights(bets, bankroll)

    return {
        "insights": [
            {
                "id": i.id,
                "category": i.category,
                "severity": i.severity,
                "title": i.title,
                "message": i.message,
                "action": i.action,
                "metric_value": i.metric_value,
                "link": i.link,
            }
            for i in insights
        ],
        "total": len(insights),
    }


# ── Bet Rating ────────────────────────────────────────────────────────

@router.post("/bet-rating")
def rate_bet_endpoint(req: BetRatingRequest):
    """Rate a bet on a 1-5 star scale (BetQL-style confidence scoring)."""
    from sba.services.insights import rate_bet

    rating = rate_bet(
        odds_american=req.odds_american,
        model_prob=req.model_probability,
        ev_pct=req.ev_pct,
        kelly=req.kelly_fraction,
        clv=req.clv,
    )
    return rating


# ── Staking ───────────────────────────────────────────────────────────

@router.post("/staking/compare")
def compare_staking(req: StakingRequest):
    """Compare all staking strategies side by side."""
    from sba.services.staking import compare_strategies

    strategies = compare_strategies(
        bankroll=req.bankroll,
        odds_decimal=req.odds_decimal,
        win_prob=req.win_probability,
        ev_pct=req.ev_pct,
        confidence=req.confidence,
        loss_streak=req.loss_streak,
    )
    return {"strategies": strategies, "bankroll": req.bankroll}


@router.post("/staking/kelly")
def kelly_stake(
    bankroll: float = Query(...),
    odds_decimal: float = Query(...),
    win_probability: float = Query(...),
    fraction: float = Query(0.25),
):
    """Calculate Kelly Criterion stake."""
    from sba.services.staking import kelly_criterion

    result = kelly_criterion(bankroll, odds_decimal, win_probability, fraction)
    return {
        "strategy": result.strategy,
        "stake": result.stake,
        "unit_pct": result.unit_size,
        "reasoning": result.reasoning,
    }


# ── Today's Performance ──────────────────────────────────────────────

@router.get("/performance/today")
def today_performance():
    """Get today's betting performance for the live dashboard widget."""
    from datetime import date

    today = date.today().isoformat()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT status, profit_loss, odds_american, market, recommended_stake
            FROM bets WHERE DATE(placed_at) = ? AND status IN ('won','lost','push')
        """, (today,)).fetchall()

        pending = conn.execute("""
            SELECT COUNT(*) as cnt FROM bets
            WHERE DATE(placed_at) = ? AND status = 'pending'
        """, (today,)).fetchone()

    total_bets = len(rows)
    wins = sum(1 for r in rows if r["status"] == "won")
    losses = sum(1 for r in rows if r["status"] == "lost")
    pushes = sum(1 for r in rows if r["status"] == "push")
    profit = sum((r["profit_loss"] or 0) for r in rows)
    wagered = sum(abs(r["recommended_stake"] or 0) for r in rows) or 1
    roi = profit / wagered * 100

    return {
        "date": today,
        "total_bets": total_bets,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "pending": pending["cnt"] if pending else 0,
        "profit": round(profit, 2),
        "wagered": round(wagered, 2),
        "roi": round(roi, 1),
        "win_rate": round(wins / total_bets * 100, 1) if total_bets > 0 else 0,
    }


# ── Equity Curve ─────────────────────────────────────────────────────

@router.get("/performance/equity-curve")
def equity_curve():
    """Get cumulative P/L equity curve for bankroll growth visualization."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DATE(placed_at) as bet_date,
                   SUM(profit_loss) as daily_pnl,
                   COUNT(*) as bets,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins
            FROM bets WHERE status IN ('won','lost','push')
            GROUP BY DATE(placed_at)
            ORDER BY bet_date
        """).fetchall()

        bankroll_row = conn.execute(
            "SELECT amount FROM bankroll_log ORDER BY created_at ASC LIMIT 1"
        ).fetchone()

    starting = bankroll_row["amount"] if bankroll_row else 1000
    cumulative = starting
    peak = starting
    curve = []

    for r in rows:
        cumulative += (r["daily_pnl"] or 0)
        peak = max(peak, cumulative)
        drawdown = (peak - cumulative) / peak * 100 if peak > 0 else 0
        curve.append({
            "date": r["bet_date"],
            "daily_pnl": round(r["daily_pnl"] or 0, 2),
            "cumulative": round(cumulative, 2),
            "bets": r["bets"],
            "wins": r["wins"],
            "drawdown_pct": round(drawdown, 1),
        })

    return {
        "starting_bankroll": starting,
        "current_value": round(cumulative, 2),
        "peak": round(peak, 2),
        "total_pnl": round(cumulative - starting, 2),
        "total_roi": round((cumulative - starting) / starting * 100, 1) if starting > 0 else 0,
        "curve": curve,
    }
