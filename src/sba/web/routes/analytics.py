"""All analytics endpoints (by-sport, by-market, by-book, by-day, heatmap, streaks, trends, advanced)."""

from __future__ import annotations

import logging
import math
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from sba.data.db import get_connection
from sba.utils.cache import cache
from sba.web.api import repo
from sba.web.errors import safe_endpoint

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])


# ── Pydantic models ─────────────────────────────────────────────────

class AnalyticsResponse(BaseModel):
    by_market: dict[str, dict]
    by_bookmaker: dict[str, dict]
    daily_pnl: list[dict]
    best_bet: dict | None
    worst_bet: dict | None
    streak: dict


# ── Helpers ──────────────────────────────────────────────────────────

def _get_settled_bets_dicts() -> list[dict]:
    """Helper to get settled bets as dicts for analytics service.

    Cached for 120s to avoid repeated full-table scans across the 7+
    analytics breakdown endpoints that all call this function.
    """
    cached_result = cache.get("settled_bets:all")
    if cached_result is not None:
        return cached_result

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT b.*, e.sport, e.home_team, e.away_team
            FROM bets b
            LEFT JOIN events e ON e.id = b.event_id
            WHERE b.status IN ('won', 'lost', 'push')
            ORDER BY b.placed_at
            LIMIT 10000
        """).fetchall()
    result = [
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
    cache.set("settled_bets:all", result, ttl=120.0)
    return result


def _row_to_dict(r) -> dict:
    return {
        "label": r.label, "bets": r.bets, "wins": r.wins, "losses": r.losses,
        "pushes": r.pushes, "profit": r.profit, "wagered": r.wagered,
        "win_rate": r.win_rate, "roi_pct": r.roi_pct, "avg_odds": r.avg_odds,
    }


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/analytics", response_model=AnalyticsResponse)
@safe_endpoint
def get_analytics():
    """Get detailed betting analytics breakdown using SQL aggregations."""
    with get_connection() as conn:
        # By market — computed in SQL instead of Python
        market_rows = conn.execute("""
            SELECT market,
                   COUNT(*) as bets,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   ROUND(SUM(profit_loss), 2) as profit,
                   ROUND(SUM(recommended_stake), 2) as staked
            FROM bets WHERE status IN ('won', 'lost', 'push')
            GROUP BY market
        """).fetchall()

        by_market = {
            r["market"]: {
                "bets": r["bets"], "wins": r["wins"],
                "profit": r["profit"] or 0, "staked": r["staked"] or 0,
                "win_rate": round(r["wins"] / max(r["bets"], 1) * 100, 1),
                "roi": round((r["profit"] or 0) / max(r["staked"] or 1, 1) * 100, 1),
            }
            for r in market_rows
        }

        # By bookmaker — computed in SQL
        book_rows = conn.execute("""
            SELECT bookmaker,
                   COUNT(*) as bets,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   ROUND(SUM(profit_loss), 2) as profit,
                   ROUND(SUM(recommended_stake), 2) as staked
            FROM bets WHERE status IN ('won', 'lost', 'push')
            GROUP BY bookmaker
        """).fetchall()

        by_bookmaker = {
            r["bookmaker"]: {
                "bets": r["bets"], "wins": r["wins"],
                "profit": r["profit"] or 0, "staked": r["staked"] or 0,
                "win_rate": round(r["wins"] / max(r["bets"], 1) * 100, 1),
                "roi": round((r["profit"] or 0) / max(r["staked"] or 1, 1) * 100, 1),
            }
            for r in book_rows
        }

        # Daily P/L — computed in SQL
        daily_rows = conn.execute("""
            SELECT DATE(placed_at) as bet_date,
                   ROUND(SUM(profit_loss), 2) as pnl
            FROM bets WHERE status IN ('won', 'lost', 'push') AND placed_at IS NOT NULL
            GROUP BY DATE(placed_at) ORDER BY bet_date
        """).fetchall()

        daily_pnl_list = [{"date": r["bet_date"], "pnl": r["pnl"] or 0} for r in daily_rows]

        # Best and worst bets — single query each
        best_row = conn.execute("""
            SELECT selection, market, odds_american, profit_loss, bookmaker
            FROM bets WHERE status IN ('won', 'lost', 'push')
            ORDER BY profit_loss DESC LIMIT 1
        """).fetchone()

        worst_row = conn.execute("""
            SELECT selection, market, odds_american, profit_loss, bookmaker
            FROM bets WHERE status IN ('won', 'lost', 'push')
            ORDER BY profit_loss ASC LIMIT 1
        """).fetchone()

        # Current streak — last N settled bets
        streak_rows = conn.execute("""
            SELECT status FROM bets
            WHERE status IN ('won', 'lost', 'push')
            ORDER BY placed_at DESC LIMIT 50
        """).fetchall()

    def row_summary(r):
        if not r:
            return None
        return {
            "selection": r["selection"], "market": r["market"],
            "odds": r["odds_american"], "profit_loss": round(r["profit_loss"], 2),
            "bookmaker": r["bookmaker"],
        }

    streak_type = ""
    streak_count = 0
    for r in streak_rows:
        if not streak_type:
            streak_type = r["status"]
            streak_count = 1
        elif r["status"] == streak_type:
            streak_count += 1
        else:
            break

    return AnalyticsResponse(
        by_market=by_market,
        by_bookmaker=by_bookmaker,
        daily_pnl=daily_pnl_list,
        best_bet=row_summary(best_row),
        worst_bet=row_summary(worst_row),
        streak={"type": streak_type, "count": streak_count},
    )


@router.get("/analytics/advanced")
@safe_endpoint
def get_advanced_analytics():
    """Get advanced performance metrics: Sharpe, max drawdown, CLV, streaks."""
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
        sum(b.expected_value or 0 for b in settled) / max(len(settled), 1) * 100, 2
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


# ── Analytics Breakdowns ─────────────────────────────────────────────

@router.get("/analytics/by-sport")
@safe_endpoint
def analytics_by_sport():
    """Performance breakdown by sport (NBA, NFL, MLB, etc.)."""
    from sba.services.analytics import breakdown_by_sport
    bets = _get_settled_bets_dicts()
    rows = breakdown_by_sport(bets)
    return {"breakdown": [_row_to_dict(r) for r in rows], "total_bets": len(bets)}


@router.get("/analytics/by-day")
@safe_endpoint
def analytics_by_day_of_week():
    """Performance breakdown by day of week."""
    from sba.services.analytics import breakdown_by_day_of_week
    bets = _get_settled_bets_dicts()
    rows = breakdown_by_day_of_week(bets)
    return {"breakdown": [_row_to_dict(r) for r in rows], "total_bets": len(bets)}


@router.get("/analytics/by-odds-range")
@safe_endpoint
def analytics_by_odds_range():
    """Performance breakdown by odds range bucket."""
    from sba.services.analytics import breakdown_by_odds_range
    bets = _get_settled_bets_dicts()
    rows = breakdown_by_odds_range(bets)
    return {"breakdown": [_row_to_dict(r) for r in rows], "total_bets": len(bets)}


@router.get("/analytics/by-market")
@safe_endpoint
def analytics_by_market_type():
    """Performance breakdown by market type."""
    from sba.services.analytics import breakdown_by_market
    bets = _get_settled_bets_dicts()
    rows = breakdown_by_market(bets)
    return {"breakdown": [_row_to_dict(r) for r in rows], "total_bets": len(bets)}


@router.get("/analytics/by-book")
@safe_endpoint
def analytics_by_bookmaker():
    """Performance breakdown by bookmaker."""
    from sba.services.analytics import breakdown_by_bookmaker
    bets = _get_settled_bets_dicts()
    rows = breakdown_by_bookmaker(bets)
    return {"breakdown": [_row_to_dict(r) for r in rows], "total_bets": len(bets)}


@router.get("/analytics/trends")
@safe_endpoint
def analytics_trends(window: int = Query(7, ge=1, le=365)):
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
@safe_endpoint
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
@safe_endpoint
def analytics_heatmap():
    """Day-of-week x hour performance heatmap."""
    from sba.services.analytics import performance_heatmap
    bets = _get_settled_bets_dicts()
    return {"heatmap": performance_heatmap(bets), "total_bets": len(bets)}
