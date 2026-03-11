"""Performance analytics endpoints: today's performance, equity curve,
sharp money, power ratings, public money, correlations, achievements,
insights, bet grading/rating, staking, momentum, daily summary, cache stats.

CLV tracking → clv.py
Simulation/backtest → simulation.py
"""

from __future__ import annotations

import csv
import io
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sba.config import get_settings
from sba.data.db import get_connection
from sba.utils.cache import cached_response
from sba.web.api import repo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["performance"])


# ── Pydantic models ─────────────────────────────────────────────────

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

    books = set()
    for b in bets:
        if b["bookmaker"]:
            books.add(b["bookmaker"])
    with get_connection() as conn2:
        sport_rows = conn2.execute("""
            SELECT DISTINCT e.sport FROM bets b
            JOIN events e ON e.id = b.event_id
            WHERE b.status IN ('won','lost','push') AND e.sport IS NOT NULL
        """).fetchall()
    sports = {r["sport"] for r in sport_rows}

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
            WHERE e.sport = ?
            ORDER BY os_h.snapshot_time DESC
            LIMIT 200
        """, (sport,)).fetchall()

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
    outcomes: list[dict] | None = None,
):
    """Analyze custom public money data."""
    from sba.services.public_money import analyze_public_money

    analysis = analyze_public_money(event_id, market, outcomes or [])
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
def get_correlation_matrix(sport: str = ""):
    """Get the known correlation matrix for SGP pricing.

    Args:
        sport: Filter by sport (nba, nfl, mlb, nhl). Empty returns all.
    """
    from sba.services.correlations import SPORT_CORRELATIONS, normalize_sport

    result = []
    for sport_key, pairs in SPORT_CORRELATIONS.items():
        if sport and normalize_sport(sport) != sport_key and sport_key != "default":
            continue
        for k, v in pairs.items():
            if v != 0:
                result.append({
                    "sport": sport_key,
                    "market_a": k[0],
                    "direction_a": k[1],
                    "market_b": k[2],
                    "direction_b": k[3],
                    "correlation": v,
                })
    return result


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


# ── Momentum & Streaks ──────────────────────────────────────────────

@router.get("/momentum")
def get_momentum():
    """Get streak analysis and momentum score for betting performance."""
    from sba.services.momentum import get_streak_analysis
    return get_streak_analysis()


@router.get("/daily-summary")
def get_daily_summary():
    """Get smart daily summary with today's performance, trends, and insights."""
    from sba.services.momentum import get_daily_summary
    return get_daily_summary()


# ── Cache Stats ──────────────────────────────────────────────────────

@router.get("/cache/stats")
def get_cache_stats():
    """Get API response cache statistics."""
    from sba.utils.cache import cache
    return cache.stats


# ── Betting Health Score ──────────────────────────────────────────

@router.get("/health-score")
@cached_response(ttl=120, prefix="health_score")
def get_health_score():
    """Get composite Betting Health Score (0-100) with component breakdown.

    Combines CLV performance, ROI sustainability, bankroll discipline,
    edge accuracy, and diversification into a single actionable score.
    """
    from sba.services.health_score import calculate_health_score
    return calculate_health_score()


# ── Correlation Warnings ──────────────────────────────────────────

@router.get("/correlation-warnings")
def get_correlation_warnings():
    """Analyze pending bets for correlated exposure and risk concentration.

    Detects same-event overlap, book concentration, temporal clustering,
    and sport concentration to help manage portfolio-level risk.
    """
    from sba.services.correlation_warnings import analyze_bet_correlations
    return analyze_bet_correlations()


# ── ROI Forecast ──────────────────────────────────────────────────

@router.get("/roi-forecast")
@cached_response(ttl=180, prefix="roi_forecast")
def get_roi_forecast():
    """Project future ROI using bootstrap resampling of historical results.

    Returns confidence intervals, break-even probability, and actionable
    recommendations based on bet history.
    """
    from sba.services.roi_forecast import forecast_roi

    bets = _get_settled_bets_dicts()
    bankroll = 0
    with get_connection() as conn:
        row = conn.execute(
            "SELECT amount FROM bankroll_log ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            bankroll = row["amount"]

    forecast = forecast_roi(bets, bankroll=bankroll or 1000)

    return {
        "current_roi": forecast.current_roi,
        "projected_roi_30": forecast.projected_roi_30,
        "projected_roi_100": forecast.projected_roi_100,
        "confidence_level": forecast.confidence_level,
        "sample_size": forecast.sample_size,
        "edge_per_bet": forecast.edge_per_bet,
        "variance": forecast.variance,
        "break_even_probability": forecast.break_even_probability,
        "risk_assessment": forecast.risk_assessment,
        "recommendations": forecast.recommendations,
        "forecast_curve": [
            {
                "bet_number": pt.bet_number,
                "projected_profit": pt.projected_profit,
                "lower_bound": pt.lower_bound,
                "upper_bound": pt.upper_bound,
                "projected_roi": pt.projected_roi,
            }
            for pt in forecast.forecast_curve
        ],
    }


# ── Bet Timing Analysis ──────────────────────────────────────────

@router.get("/bet-timing")
@cached_response(ttl=120, prefix="bet_timing")
def get_bet_timing():
    """Analyze when you place your most profitable bets.

    Breaks down performance by hour of day and day of week to find
    optimal betting windows.
    """
    from sba.services.bet_timing import analyze_bet_timing

    bets = _get_settled_bets_dicts()
    analysis = analyze_bet_timing(bets)

    def _window_dict(w):
        return {
            "label": w.label,
            "bets": w.bets,
            "wins": w.wins,
            "losses": w.losses,
            "profit": w.profit,
            "roi_pct": w.roi_pct,
            "win_rate": w.win_rate,
            "score": w.score,
        }

    return {
        "optimal_window": analysis.optimal_window,
        "timing_score": analysis.timing_score,
        "best_hours": [_window_dict(w) for w in analysis.best_hours],
        "worst_hours": [_window_dict(w) for w in analysis.worst_hours],
        "best_days": [_window_dict(w) for w in analysis.best_days],
        "by_hour": [_window_dict(w) for w in analysis.by_hour],
        "by_day": [_window_dict(w) for w in analysis.by_day],
        "recommendations": analysis.recommendations,
    }


# ── Risk-Adjusted Metrics ────────────────────────────────────────

@router.get("/risk-metrics")
@cached_response(ttl=120, prefix="risk_metrics")
def get_risk_metrics():
    """Get institutional-grade risk-adjusted performance metrics.

    Includes Sharpe ratio, Sortino ratio, Calmar ratio, profit factor,
    drawdown analysis, and win/loss distribution statistics.
    """
    from sba.services.risk_metrics import calculate_risk_metrics

    bets = _get_settled_bets_dicts()
    bankroll = 0
    with get_connection() as conn:
        row = conn.execute(
            "SELECT amount FROM bankroll_log ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            bankroll = row["amount"]

    metrics = calculate_risk_metrics(bets, bankroll=bankroll or 1000)

    return {
        "sharpe_ratio": metrics.sharpe_ratio,
        "sortino_ratio": metrics.sortino_ratio,
        "calmar_ratio": metrics.calmar_ratio,
        "profit_factor": metrics.profit_factor,
        "kelly_edge": metrics.kelly_edge,
        "roi_pct": metrics.roi_pct,
        "total_profit": metrics.total_profit,
        "total_bets": metrics.total_bets,
        "risk_grade": metrics.risk_grade,
        "risk_summary": metrics.risk_summary,
        "max_drawdown": {
            "amount": metrics.max_drawdown.max_drawdown,
            "pct": metrics.max_drawdown.max_drawdown_pct,
            "current_amount": metrics.max_drawdown.current_drawdown,
            "current_pct": metrics.max_drawdown.current_drawdown_pct,
            "avg_pct": metrics.max_drawdown.avg_drawdown,
            "duration_bets": metrics.max_drawdown.drawdown_duration,
            "recovery_bets": metrics.max_drawdown.recovery_time,
        },
        "distribution": {
            "avg_win": metrics.distribution.avg_win,
            "avg_loss": metrics.distribution.avg_loss,
            "median_win": metrics.distribution.median_win,
            "median_loss": metrics.distribution.median_loss,
            "largest_win": metrics.distribution.largest_win,
            "largest_loss": metrics.distribution.largest_loss,
            "win_loss_ratio": metrics.distribution.win_loss_ratio,
            "skewness": metrics.distribution.skewness,
            "expectancy": metrics.distribution.expectancy,
        },
    }


# ── Dashboard Summary ──────────────────────────────────────────

@router.get("/dashboard/summary")
def get_dashboard_summary():
    """Aggregated dashboard data in a single API call.

    Returns today's P&L, health score, bankroll status, recent insights,
    achievement summary, and active signals — reducing N+1 API calls
    from the dashboard to a single request.
    """
    from datetime import date as _date

    from sba.services.health_score import calculate_health_score
    from sba.services.insights import generate_insights
    from sba.services.momentum import get_streak_analysis

    today = _date.today().isoformat()

    with get_connection() as conn:
        # Today's bets
        today_rows = conn.execute("""
            SELECT status, profit_loss, recommended_stake
            FROM bets WHERE DATE(placed_at) = ? AND status IN ('won','lost','push')
        """, (today,)).fetchall()

        pending_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM bets WHERE DATE(placed_at) = ? AND status = 'pending'",
            (today,)
        ).fetchone()["cnt"]

        # Lifetime stats
        lifetime = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   SUM(profit_loss) as profit,
                   SUM(ABS(recommended_stake)) as wagered
            FROM bets WHERE status IN ('won','lost','push')
        """).fetchone()

        # Bankroll
        bankroll_row = conn.execute(
            "SELECT amount FROM bankroll_log ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

        # DB status
        events = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
        odds_snaps = conn.execute("SELECT COUNT(*) as c FROM odds_snapshots").fetchone()["c"]

    # Today
    today_profit = sum(r["profit_loss"] or 0 for r in today_rows)
    today_bets = len(today_rows)
    today_wins = sum(1 for r in today_rows if r["status"] == "won")
    today_wagered = sum(abs(r["recommended_stake"] or 0) for r in today_rows) or 1

    # Lifetime
    lt_total = lifetime["total"] or 0
    lt_wins = lifetime["wins"] or 0
    lt_profit = lifetime["profit"] or 0
    lt_wagered = lifetime["wagered"] or 1

    # Health score (lightweight)
    health = calculate_health_score()

    # Streaks
    streaks = get_streak_analysis()

    # Insights (use settled bets)
    settled = _get_settled_bets_dicts()
    bankroll = bankroll_row["amount"] if bankroll_row else 1000
    insights = generate_insights(settled, bankroll)

    return {
        "today": {
            "profit": round(today_profit, 2),
            "bets": today_bets,
            "wins": today_wins,
            "losses": today_bets - today_wins,
            "pending": pending_count,
            "roi_pct": round(today_profit / today_wagered * 100, 1),
            "win_rate": round(today_wins / today_bets * 100, 1) if today_bets else 0,
        },
        "lifetime": {
            "total_bets": lt_total,
            "wins": lt_wins,
            "profit": round(lt_profit, 2),
            "roi_pct": round(lt_profit / lt_wagered * 100, 1),
            "win_rate": round(lt_wins / lt_total * 100, 1) if lt_total else 0,
        },
        "bankroll": {
            "current": round(bankroll, 2),
        },
        "health_score": {
            "score": health.get("score"),
            "grade": health.get("grade", "N/A"),
        },
        "streaks": {
            "current": streaks.get("current_streak", 0),
            "current_type": streaks.get("streak_type", "none"),
            "momentum": streaks.get("momentum_score", 0),
        },
        "insights_count": len(insights),
        "top_insights": [
            {"title": i.title, "severity": i.severity, "action": i.action}
            for i in insights[:3]
        ],
        "data_status": {
            "events": events,
            "odds_snapshots": odds_snaps,
        },
    }


# ── Performance Digest ──────────────────────────────────────────

@router.get("/performance/digest")
def get_performance_digest(period: str = "weekly"):
    """Get structured performance digest (weekly or monthly).

    Returns comprehensive performance report with trends, breakdowns,
    highlights, and a letter grade — like Action Network's weekly recap.
    """
    from sba.services.performance_digest import generate_digest

    digest = generate_digest(period)

    def _period_dict(p):
        if not p:
            return None
        return {
            "label": p.label,
            "start_date": p.start_date,
            "end_date": p.end_date,
            "total_bets": p.total_bets,
            "wins": p.wins,
            "losses": p.losses,
            "pushes": p.pushes,
            "profit": p.profit,
            "wagered": p.wagered,
            "roi_pct": p.roi_pct,
            "win_rate": p.win_rate,
            "avg_odds": p.avg_odds,
            "best_bet": p.best_bet,
            "worst_bet": p.worst_bet,
        }

    return {
        "period": digest.period,
        "grade": digest.grade,
        "grade_trend": digest.grade_trend,
        "current": _period_dict(digest.current),
        "previous": _period_dict(digest.previous),
        "trends": [
            {
                "metric": t.metric,
                "current": t.current,
                "previous": t.previous,
                "change": t.change,
                "direction": t.direction,
                "sentiment": t.sentiment,
                "description": t.description,
            }
            for t in digest.trends
        ],
        "streaks": digest.streaks,
        "by_sport": digest.by_sport,
        "by_market": digest.by_market,
        "by_book": digest.by_book,
        "highlights": digest.highlights,
        "warnings": digest.warnings,
    }


# ── Analytics Export ─────────────────────────────────────────────────


@router.get("/analytics/export")
def api_analytics_export(
    format: str = Query("csv", pattern="^(csv|json)$"),
    status: str = Query("settled", pattern="^(settled|all|pending)$"),
):
    """Export bet history as CSV or JSON.

    Supports filtering by status:
    - settled: won/lost/push only (default)
    - pending: pending bets only
    - all: everything
    """
    with get_connection() as conn:
        if status == "settled":
            rows = conn.execute(
                "SELECT * FROM bets WHERE status IN ('won','lost','push') ORDER BY placed_at DESC"
            ).fetchall()
        elif status == "pending":
            rows = conn.execute(
                "SELECT * FROM bets WHERE status = 'pending' ORDER BY placed_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM bets ORDER BY placed_at DESC"
            ).fetchall()

    if not rows:
        if format == "json":
            return {"bets": [], "count": 0}
        # Empty CSV with headers
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "event_id", "selection", "market", "bookmaker",
                         "odds_american", "odds_decimal", "recommended_stake",
                         "status", "profit_loss", "placed_at"])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=bets_export.csv"},
        )

    columns = rows[0].keys()

    if format == "json":
        return {
            "bets": [dict(zip(columns, row)) for row in rows],
            "count": len(rows),
        }

    # CSV export
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row[col] for col in columns])
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bets_export.csv"},
    )
