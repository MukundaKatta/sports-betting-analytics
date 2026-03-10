"""Advanced analytics and trend analysis engine.

Provides world-class performance breakdowns by sport, day-of-week,
odds range, rolling trends, and streak analysis — features found
in platforms like Trademate, BetQL, and Action Network PRO.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Odds range buckets for analysis
ODDS_RANGES = [
    ("Heavy Favorite", -1000, -201),
    ("Moderate Favorite", -200, -131),
    ("Slight Favorite", -130, -101),
    ("Pick'em", -100, 100),
    ("Slight Underdog", 101, 150),
    ("Moderate Underdog", 151, 250),
    ("Big Underdog", 251, 500),
    ("Long Shot", 501, 10000),
]

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass
class BreakdownRow:
    """A single row in a performance breakdown."""
    label: str
    bets: int = 0
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    profit: float = 0.0
    wagered: float = 0.0
    win_rate: float = 0.0
    roi_pct: float = 0.0
    avg_odds: float = 0.0
    clv_avg: float = 0.0


@dataclass
class TrendPoint:
    """A single point in a rolling trend."""
    date: str
    profit: float
    cumulative: float
    win_rate: float
    roi: float
    bets: int


@dataclass
class StreakInfo:
    """Detailed streak analysis."""
    current_type: str  # "win", "loss", "none"
    current_length: int
    longest_win: int
    longest_loss: int
    avg_win_streak: float
    avg_loss_streak: float
    win_streaks: list[int] = field(default_factory=list)
    loss_streaks: list[int] = field(default_factory=list)
    recovery_avg: float = 0.0  # avg bets to recover from loss streak


def _compute_row(label: str, bets: list[dict]) -> BreakdownRow:
    """Compute stats for a group of bets."""
    if not bets:
        return BreakdownRow(label=label)

    wins = sum(1 for b in bets if b["status"] in ("won", "win"))
    losses = sum(1 for b in bets if b["status"] in ("lost", "loss"))
    pushes = sum(1 for b in bets if b["status"] == "push")
    profit = sum(b.get("profit_loss", 0) or 0 for b in bets)
    wagered = sum(b.get("stake", 0) or 0 for b in bets)
    odds_sum = sum(b.get("odds_american", 0) or 0 for b in bets)

    total = wins + losses
    return BreakdownRow(
        label=label,
        bets=len(bets),
        wins=wins,
        losses=losses,
        pushes=pushes,
        profit=round(profit, 2),
        wagered=round(wagered, 2),
        win_rate=round(wins / total * 100, 1) if total > 0 else 0,
        roi_pct=round(profit / wagered * 100, 1) if wagered > 0 else 0,
        avg_odds=round(odds_sum / len(bets)) if bets else 0,
    )


def breakdown_by_sport(bets: list[dict]) -> list[BreakdownRow]:
    """Performance breakdown by sport."""
    by_sport: dict[str, list] = defaultdict(list)
    for b in bets:
        sport = b.get("sport", "Unknown") or "Unknown"
        by_sport[sport].append(b)

    rows = [_compute_row(sport, group) for sport, group in sorted(by_sport.items())]
    rows.sort(key=lambda r: r.profit, reverse=True)
    return rows


def breakdown_by_day_of_week(bets: list[dict]) -> list[BreakdownRow]:
    """Performance breakdown by day of week."""
    by_day: dict[int, list] = defaultdict(list)
    for b in bets:
        placed = b.get("placed_at")
        if placed:
            if isinstance(placed, str):
                try:
                    placed = datetime.fromisoformat(placed)
                except (ValueError, TypeError):
                    continue
            by_day[placed.weekday()].append(b)

    return [_compute_row(DAY_NAMES[i], by_day.get(i, [])) for i in range(7)]


def breakdown_by_odds_range(bets: list[dict]) -> list[BreakdownRow]:
    """Performance breakdown by odds range bucket."""
    buckets: dict[str, list] = defaultdict(list)

    for b in bets:
        odds = b.get("odds_american", 0) or 0
        placed = False
        for label, lo, hi in ODDS_RANGES:
            if lo <= odds <= hi:
                buckets[label].append(b)
                placed = True
                break
        if not placed:
            buckets["Other"].append(b)

    return [
        _compute_row(label, buckets.get(label, []))
        for label, _, _ in ODDS_RANGES
        if buckets.get(label)
    ]


def breakdown_by_market(bets: list[dict]) -> list[BreakdownRow]:
    """Performance breakdown by market type."""
    by_market: dict[str, list] = defaultdict(list)
    for b in bets:
        market = b.get("market", "unknown") or "unknown"
        by_market[market].append(b)

    rows = [_compute_row(m, group) for m, group in sorted(by_market.items())]
    rows.sort(key=lambda r: r.profit, reverse=True)
    return rows


def breakdown_by_bookmaker(bets: list[dict]) -> list[BreakdownRow]:
    """Performance breakdown by bookmaker."""
    by_book: dict[str, list] = defaultdict(list)
    for b in bets:
        book = b.get("bookmaker", "unknown") or "unknown"
        by_book[book].append(b)

    rows = [_compute_row(bk, group) for bk, group in sorted(by_book.items())]
    rows.sort(key=lambda r: r.profit, reverse=True)
    return rows


def rolling_trends(bets: list[dict], window: int = 7) -> list[TrendPoint]:
    """Calculate rolling performance trends over time.

    Groups bets by date and computes rolling averages over `window` days.
    """
    by_date: dict[str, list] = defaultdict(list)
    for b in bets:
        placed = b.get("placed_at")
        if placed:
            if isinstance(placed, str):
                try:
                    placed = datetime.fromisoformat(placed)
                except (ValueError, TypeError):
                    continue
            by_date[placed.strftime("%Y-%m-%d")].append(b)

    if not by_date:
        return []

    sorted_dates = sorted(by_date.keys())
    points = []
    cumulative = 0.0

    for date_str in sorted_dates:
        day_bets = by_date[date_str]
        day_profit = sum(b.get("profit_loss", 0) or 0 for b in day_bets)
        day_wins = sum(1 for b in day_bets if b.get("status") in ("won", "win"))
        day_total = sum(1 for b in day_bets if b.get("status") in ("won", "win", "lost", "loss"))
        day_wagered = sum(b.get("stake", 0) or 0 for b in day_bets)
        cumulative += day_profit

        points.append(TrendPoint(
            date=date_str,
            profit=round(day_profit, 2),
            cumulative=round(cumulative, 2),
            win_rate=round(day_wins / day_total * 100, 1) if day_total > 0 else 0,
            roi=round(day_profit / day_wagered * 100, 1) if day_wagered > 0 else 0,
            bets=len(day_bets),
        ))

    return points


def analyze_streaks(bets: list[dict]) -> StreakInfo:
    """Detailed streak analysis with recovery metrics."""
    if not bets:
        return StreakInfo(current_type="none", current_length=0,
                         longest_win=0, longest_loss=0,
                         avg_win_streak=0, avg_loss_streak=0)

    win_streaks = []
    loss_streaks = []
    current_type = ""
    current_length = 0
    recovery_bets = []
    in_recovery = False
    recovery_count = 0

    for b in bets:
        status = b.get("status", "")
        if status in ("won", "win"):
            if current_type == "win":
                current_length += 1
            else:
                if current_type == "loss":
                    loss_streaks.append(current_length)
                    in_recovery = True
                    recovery_count = 0
                current_type = "win"
                current_length = 1
            if in_recovery:
                recovery_count += 1
        elif status in ("lost", "loss"):
            if current_type == "loss":
                current_length += 1
            else:
                if current_type == "win":
                    win_streaks.append(current_length)
                    if in_recovery:
                        recovery_bets.append(recovery_count)
                        in_recovery = False
                current_type = "loss"
                current_length = 1

    # Final streak
    if current_type == "win":
        win_streaks.append(current_length)
    elif current_type == "loss":
        loss_streaks.append(current_length)

    longest_win = max(win_streaks) if win_streaks else 0
    longest_loss = max(loss_streaks) if loss_streaks else 0
    avg_win = sum(win_streaks) / len(win_streaks) if win_streaks else 0
    avg_loss = sum(loss_streaks) / len(loss_streaks) if loss_streaks else 0
    avg_recovery = sum(recovery_bets) / len(recovery_bets) if recovery_bets else 0

    return StreakInfo(
        current_type=current_type or "none",
        current_length=current_length,
        longest_win=longest_win,
        longest_loss=longest_loss,
        avg_win_streak=round(avg_win, 1),
        avg_loss_streak=round(avg_loss, 1),
        win_streaks=win_streaks,
        loss_streaks=loss_streaks,
        recovery_avg=round(avg_recovery, 1),
    )


def performance_heatmap(bets: list[dict]) -> list[dict]:
    """Generate a day-of-week × hour heatmap of performance.

    Returns a list of {day, hour, bets, profit, win_rate} entries.
    """
    grid: dict[tuple, list] = defaultdict(list)
    for b in bets:
        placed = b.get("placed_at")
        if placed:
            if isinstance(placed, str):
                try:
                    placed = datetime.fromisoformat(placed)
                except (ValueError, TypeError):
                    continue
            grid[(placed.weekday(), placed.hour)].append(b)

    result = []
    for (day, hour), group in sorted(grid.items()):
        wins = sum(1 for b in group if b.get("status") in ("won", "win"))
        total = sum(1 for b in group if b.get("status") in ("won", "win", "lost", "loss"))
        profit = sum(b.get("profit_loss", 0) or 0 for b in group)
        result.append({
            "day": DAY_NAMES[day],
            "day_num": day,
            "hour": hour,
            "bets": len(group),
            "profit": round(profit, 2),
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
        })

    return result
