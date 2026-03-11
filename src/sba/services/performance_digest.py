"""Performance digest — structured weekly/monthly performance summaries.

Generates comprehensive performance reports with trends, comparisons,
and actionable takeaways. Inspired by Action Network's weekly recaps
and Outlier's performance reports.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sba.data.db import get_connection


@dataclass
class PeriodStats:
    """Stats for a time period."""
    label: str
    start_date: str
    end_date: str
    total_bets: int
    wins: int
    losses: int
    pushes: int
    profit: float
    wagered: float
    roi_pct: float
    win_rate: float
    avg_odds: int
    best_bet: dict | None = None
    worst_bet: dict | None = None


@dataclass
class TrendIndicator:
    """A single trend metric with direction."""
    metric: str
    current: float
    previous: float
    change: float
    direction: str  # "up", "down", "flat"
    sentiment: str  # "positive", "negative", "neutral"
    description: str


@dataclass
class PerformanceDigest:
    """Complete performance digest."""
    period: str  # "weekly" or "monthly"
    current: PeriodStats
    previous: PeriodStats | None
    trends: list[TrendIndicator]
    streaks: dict
    by_sport: list[dict]
    by_market: list[dict]
    by_book: list[dict]
    highlights: list[str]
    warnings: list[str]
    grade: str  # A+ through F
    grade_trend: str  # "improving", "declining", "stable"


def generate_digest(period: str = "weekly") -> PerformanceDigest:
    """Generate a performance digest for the given period.

    Args:
        period: "weekly" or "monthly"
    """
    today = date.today()

    if period == "weekly":
        current_start = today - timedelta(days=today.weekday())  # Monday
        current_end = today
        prev_start = current_start - timedelta(days=7)
        prev_end = current_start - timedelta(days=1)
    else:  # monthly
        current_start = today.replace(day=1)
        current_end = today
        prev_end = current_start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)

    with get_connection() as conn:
        current_bets = _fetch_bets(conn, current_start.isoformat(), current_end.isoformat())
        prev_bets = _fetch_bets(conn, prev_start.isoformat(), prev_end.isoformat())
        all_settled = conn.execute("""
            SELECT b.*, e.sport FROM bets b
            LEFT JOIN events e ON e.id = b.event_id
            WHERE b.status IN ('won', 'lost', 'push')
            ORDER BY b.placed_at DESC
        """).fetchall()

    current_stats = _compute_stats(
        f"This {'Week' if period == 'weekly' else 'Month'}",
        current_start.isoformat(), current_end.isoformat(), current_bets,
    )
    prev_stats = _compute_stats(
        f"Last {'Week' if period == 'weekly' else 'Month'}",
        prev_start.isoformat(), prev_end.isoformat(), prev_bets,
    ) if prev_bets else None

    trends = _compute_trends(current_stats, prev_stats)
    streaks = _compute_streaks(all_settled)
    by_sport = _breakdown_by(current_bets, "sport")
    by_market = _breakdown_by(current_bets, "market")
    by_book = _breakdown_by(current_bets, "bookmaker")
    highlights, warnings = _generate_commentary(current_stats, prev_stats, trends, streaks)
    grade = _compute_period_grade(current_stats)

    grade_trend = "stable"
    if prev_stats:
        prev_grade_val = _grade_value(prev_stats)
        curr_grade_val = _grade_value(current_stats)
        if curr_grade_val > prev_grade_val + 5:
            grade_trend = "improving"
        elif curr_grade_val < prev_grade_val - 5:
            grade_trend = "declining"

    return PerformanceDigest(
        period=period,
        current=current_stats,
        previous=prev_stats,
        trends=trends,
        streaks=streaks,
        by_sport=by_sport,
        by_market=by_market,
        by_book=by_book,
        highlights=highlights,
        warnings=warnings,
        grade=grade,
        grade_trend=grade_trend,
    )


def _fetch_bets(conn, start: str, end: str) -> list:
    return conn.execute("""
        SELECT b.*, e.sport, e.home_team, e.away_team
        FROM bets b
        LEFT JOIN events e ON e.id = b.event_id
        WHERE b.status IN ('won', 'lost', 'push')
          AND DATE(b.placed_at) BETWEEN ? AND ?
        ORDER BY b.placed_at
    """, (start, end)).fetchall()


def _compute_stats(label: str, start: str, end: str, bets: list) -> PeriodStats:
    wins = sum(1 for b in bets if b["status"] == "won")
    losses = sum(1 for b in bets if b["status"] == "lost")
    pushes = sum(1 for b in bets if b["status"] == "push")
    profit = sum(b["profit_loss"] or 0 for b in bets)
    wagered = sum(abs(b["recommended_stake"] or 0) for b in bets) or 1
    roi = profit / wagered * 100
    win_rate = wins / len(bets) * 100 if bets else 0
    odds_list = [b["odds_american"] or 0 for b in bets if b["odds_american"]]
    avg_odds = round(sum(odds_list) / len(odds_list)) if odds_list else 0

    best = max(bets, key=lambda b: b["profit_loss"] or 0) if bets else None
    worst = min(bets, key=lambda b: b["profit_loss"] or 0) if bets else None

    def _bet_summary(b):
        if not b:
            return None
        return {
            "selection": b["selection"],
            "profit": round(b["profit_loss"] or 0, 2),
            "odds": b["odds_american"],
            "matchup": f"{b['away_team'] if 'away_team' in b.keys() else '?'} @ {b['home_team'] if 'home_team' in b.keys() else '?'}",
        }

    return PeriodStats(
        label=label, start_date=start, end_date=end,
        total_bets=len(bets), wins=wins, losses=losses, pushes=pushes,
        profit=round(profit, 2), wagered=round(wagered, 2),
        roi_pct=round(roi, 1), win_rate=round(win_rate, 1),
        avg_odds=avg_odds,
        best_bet=_bet_summary(best),
        worst_bet=_bet_summary(worst),
    )


def _compute_trends(current: PeriodStats, previous: PeriodStats | None) -> list[TrendIndicator]:
    if not previous or previous.total_bets == 0:
        return []

    trends = []
    metrics = [
        ("ROI", current.roi_pct, previous.roi_pct, "%", True),
        ("Win Rate", current.win_rate, previous.win_rate, "%", True),
        ("Volume", current.total_bets, previous.total_bets, " bets", True),
        ("Profit", current.profit, previous.profit, "", True),
    ]

    for name, curr, prev, suffix, higher_is_good in metrics:
        change = curr - prev
        if abs(change) < 0.1:
            direction = "flat"
            sentiment = "neutral"
        elif change > 0:
            direction = "up"
            sentiment = "positive" if higher_is_good else "negative"
        else:
            direction = "down"
            sentiment = "negative" if higher_is_good else "positive"

        arrow = {"up": "+", "down": "", "flat": ""}[direction]
        trends.append(TrendIndicator(
            metric=name,
            current=round(curr, 1),
            previous=round(prev, 1),
            change=round(change, 1),
            direction=direction,
            sentiment=sentiment,
            description=f"{name}: {curr:.1f}{suffix} ({arrow}{change:.1f}{suffix} vs prior period)",
        ))

    return trends


def _compute_streaks(bets: list) -> dict:
    if not bets:
        return {"current": 0, "current_type": "none", "longest_win": 0, "longest_loss": 0}

    current_streak = 0
    current_type = "none"
    longest_win = 0
    longest_loss = 0
    win_run = 0
    loss_run = 0

    for b in reversed(list(bets)):  # oldest first
        if b["status"] == "won":
            win_run += 1
            loss_run = 0
            longest_win = max(longest_win, win_run)
        elif b["status"] == "lost":
            loss_run += 1
            win_run = 0
            longest_loss = max(longest_loss, loss_run)
        else:
            win_run = 0
            loss_run = 0

    # Current streak (from most recent)
    for b in bets:
        if current_type == "none":
            current_type = b["status"]
            current_streak = 1
        elif b["status"] == current_type:
            current_streak += 1
        else:
            break

    return {
        "current": current_streak,
        "current_type": current_type,
        "longest_win": longest_win,
        "longest_loss": longest_loss,
    }


def _breakdown_by(bets: list, key: str) -> list[dict]:
    buckets: dict[str, list] = {}
    for b in bets:
        val = (b[key] if key in b.keys() else None) or "unknown"
        if isinstance(val, str) and key == "sport":
            val = val.split("_")[-1].upper() if "_" in val else val.upper()
        buckets.setdefault(val, []).append(b)

    result = []
    for name, group in buckets.items():
        wins = sum(1 for b in group if b["status"] == "won")
        profit = sum(b["profit_loss"] or 0 for b in group)
        wagered = sum(abs(b["recommended_stake"] or 0) for b in group) or 1
        result.append({
            "name": name,
            "bets": len(group),
            "wins": wins,
            "win_rate": round(wins / len(group) * 100, 1),
            "profit": round(profit, 2),
            "roi_pct": round(profit / wagered * 100, 1),
        })

    result.sort(key=lambda x: x["profit"], reverse=True)
    return result


def _generate_commentary(
    current: PeriodStats, previous: PeriodStats | None,
    trends: list[TrendIndicator], streaks: dict,
) -> tuple[list[str], list[str]]:
    highlights = []
    warnings = []

    if current.total_bets == 0:
        warnings.append("No bets placed this period — stay active to maintain your edge.")
        return highlights, warnings

    if current.roi_pct > 10:
        highlights.append(f"Exceptional {current.roi_pct}% ROI this period.")
    elif current.roi_pct > 0:
        highlights.append(f"Profitable period with {current.roi_pct}% ROI.")

    if current.win_rate > 55:
        highlights.append(f"Strong {current.win_rate}% win rate.")

    if current.best_bet and current.best_bet["profit"] > 0:
        highlights.append(f"Best bet: {current.best_bet['selection']} ({current.best_bet['matchup']}) +${current.best_bet['profit']:.0f}.")

    if streaks["current_type"] == "won" and streaks["current"] >= 5:
        highlights.append(f"Currently on a {streaks['current']}-bet win streak!")

    # Warnings
    if current.roi_pct < -10:
        warnings.append(f"Tough period with {current.roi_pct}% ROI. Review your strategy and consider reducing stake sizes.")

    if current.win_rate < 40 and current.total_bets >= 10:
        warnings.append(f"Win rate of {current.win_rate}% is below average. Focus on higher-confidence plays.")

    if streaks["current_type"] == "lost" and streaks["current"] >= 4:
        warnings.append(f"Currently on a {streaks['current']}-bet losing streak. Consider a cooling period.")

    for t in trends:
        if t.metric == "ROI" and t.direction == "down" and t.change < -5:
            warnings.append(f"ROI declined {abs(t.change):.1f}% vs last period.")
        elif t.metric == "ROI" and t.direction == "up" and t.change > 5:
            highlights.append(f"ROI improved {t.change:.1f}% vs last period.")

    if not highlights:
        highlights.append("Keep tracking bets to build your performance history.")

    return highlights, warnings


def _grade_value(stats: PeriodStats) -> float:
    """Numeric grade value for trend comparison."""
    if stats.total_bets == 0:
        return 0
    score = 0
    score += min(30, max(0, stats.roi_pct * 3))  # ROI contribution
    score += min(30, max(0, (stats.win_rate - 40) * 1.5))  # Win rate
    score += min(20, stats.total_bets)  # Volume (up to 20 bets)
    score += min(20, max(0, stats.profit / 10))  # Raw profit
    return max(0, min(100, score))


def _compute_period_grade(stats: PeriodStats) -> str:
    score = _grade_value(stats)
    if score >= 85:
        return "A+"
    elif score >= 75:
        return "A"
    elif score >= 65:
        return "B+"
    elif score >= 55:
        return "B"
    elif score >= 45:
        return "C+"
    elif score >= 35:
        return "C"
    elif score >= 25:
        return "D"
    else:
        return "F"
