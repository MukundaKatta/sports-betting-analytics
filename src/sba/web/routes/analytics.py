"""All analytics endpoints (by-sport, by-market, by-book, by-day, heatmap, streaks, trends, advanced)."""

from __future__ import annotations

import logging
import math
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from sba.data.db import get_connection
from sba.web.api import repo

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


def _row_to_dict(r) -> dict:
    return {
        "label": r.label, "bets": r.bets, "wins": r.wins, "losses": r.losses,
        "pushes": r.pushes, "profit": r.profit, "wagered": r.wagered,
        "win_rate": r.win_rate, "roi_pct": r.roi_pct, "avg_odds": r.avg_odds,
    }


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/analytics", response_model=AnalyticsResponse)
def get_analytics():
    """Get detailed betting analytics breakdown."""
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


@router.get("/analytics/advanced")
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
    """Day-of-week x hour performance heatmap."""
    from sba.services.analytics import performance_heatmap
    bets = _get_settled_bets_dicts()
    return {"heatmap": performance_heatmap(bets), "total_bets": len(bets)}
