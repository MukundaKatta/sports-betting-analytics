"""Bet timing analysis — find optimal time windows for placing bets.

Analyzes historical performance by:
- Hour of day
- Day of week
- Time before event start
- Line movement timing
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TimingWindow:
    """Performance within a specific time window."""
    label: str
    bets: int
    wins: int
    losses: int
    profit: float
    roi_pct: float
    win_rate: float
    avg_clv: float
    score: float  # composite quality score 0-100


@dataclass
class TimingAnalysis:
    """Complete bet timing analysis."""
    best_hours: list[TimingWindow]
    worst_hours: list[TimingWindow]
    best_days: list[TimingWindow]
    by_hour: list[TimingWindow]
    by_day: list[TimingWindow]
    optimal_window: str
    timing_score: float  # 0-100 how well user times bets
    recommendations: list[str]


DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _compute_window(label: str, bets: list[dict]) -> TimingWindow:
    """Compute timing stats for a group of bets."""
    if not bets:
        return TimingWindow(label=label, bets=0, wins=0, losses=0,
                            profit=0, roi_pct=0, win_rate=0, avg_clv=0, score=0)

    wins = sum(1 for b in bets if b.get("status") in ("won", "win"))
    losses = sum(1 for b in bets if b.get("status") in ("lost", "loss"))
    total_decided = wins + losses
    profit = sum(b.get("profit_loss", 0) or 0 for b in bets)
    wagered = sum(abs(b.get("stake", 0) or b.get("recommended_stake", 0) or 0) for b in bets) or 1
    roi = profit / wagered * 100
    win_rate = wins / total_decided * 100 if total_decided > 0 else 0
    avg_clv = sum(b.get("clv", 0) or 0 for b in bets) / len(bets)

    # Composite score: weighted combination of ROI, win rate, and sample size
    sample_factor = min(len(bets) / 20, 1.0)  # scales up to 20 bets
    roi_score = max(0, min(100, 50 + roi * 5))
    wr_score = max(0, min(100, win_rate))
    score = (roi_score * 0.5 + wr_score * 0.3 + sample_factor * 20) * sample_factor

    return TimingWindow(
        label=label,
        bets=len(bets),
        wins=wins,
        losses=losses,
        profit=round(profit, 2),
        roi_pct=round(roi, 1),
        win_rate=round(win_rate, 1),
        avg_clv=round(avg_clv, 2),
        score=round(score, 1),
    )


def analyze_bet_timing(bets: list[dict]) -> TimingAnalysis:
    """Analyze when the user places their most profitable bets.

    Args:
        bets: List of settled bet dicts with 'placed_at', 'profit_loss', 'stake'.
    """
    by_hour: dict[int, list] = defaultdict(list)
    by_day: dict[int, list] = defaultdict(list)

    for b in bets:
        placed = b.get("placed_at")
        if not placed:
            continue
        if isinstance(placed, str):
            try:
                placed = datetime.fromisoformat(placed)
            except (ValueError, TypeError):
                continue
        by_hour[placed.hour].append(b)
        by_day[placed.weekday()].append(b)

    # Build hourly analysis
    hour_windows = []
    for h in range(24):
        label = f"{h:02d}:00-{h:02d}:59"
        hour_windows.append(_compute_window(label, by_hour.get(h, [])))

    # Build daily analysis
    day_windows = []
    for d in range(7):
        day_windows.append(_compute_window(DAY_NAMES[d], by_day.get(d, [])))

    # Find best/worst (only windows with enough data)
    active_hours = [w for w in hour_windows if w.bets >= 3]
    active_days = [w for w in day_windows if w.bets >= 3]

    best_hours = sorted(active_hours, key=lambda w: w.score, reverse=True)[:3]
    worst_hours = sorted(active_hours, key=lambda w: w.score)[:3]
    best_days = sorted(active_days, key=lambda w: w.score, reverse=True)[:3]

    # Compute overall timing score
    if active_hours:
        avg_score = sum(w.score for w in active_hours) / len(active_hours)
        timing_score = min(100, avg_score * 1.2)
    else:
        timing_score = 0

    # Generate optimal window description
    if best_hours and best_days:
        optimal = f"{best_days[0].label}s, {best_hours[0].label}"
    elif best_hours:
        optimal = best_hours[0].label
    elif best_days:
        optimal = f"{best_days[0].label}s"
    else:
        optimal = "Insufficient data"

    # Recommendations
    recs = []
    if best_hours and worst_hours:
        best_roi = best_hours[0].roi_pct
        worst_roi = worst_hours[0].roi_pct
        if best_roi - worst_roi > 10:
            recs.append(
                f"Your best hour ({best_hours[0].label}) has {best_roi:.0f}% ROI "
                f"vs worst ({worst_hours[0].label}) at {worst_roi:.0f}%. "
                f"Consider timing bets during peak hours."
            )

    if best_days and len(active_days) >= 3:
        profitable_days = [d for d in active_days if d.roi_pct > 0]
        losing_days = [d for d in active_days if d.roi_pct < -5]
        if losing_days:
            recs.append(
                f"Avoid betting on {losing_days[0].label}s — "
                f"{losing_days[0].roi_pct:.0f}% ROI across {losing_days[0].bets} bets."
            )
        if profitable_days:
            recs.append(
                f"Focus on {profitable_days[0].label}s — "
                f"{profitable_days[0].roi_pct:.0f}% ROI across {profitable_days[0].bets} bets."
            )

    if not bets:
        recs.append("Start tracking bets to unlock timing analysis.")
    elif len(bets) < 30:
        recs.append("Place more bets for statistically meaningful timing insights.")

    return TimingAnalysis(
        best_hours=best_hours,
        worst_hours=worst_hours,
        best_days=best_days,
        by_hour=hour_windows,
        by_day=day_windows,
        optimal_window=optimal,
        timing_score=round(timing_score, 1),
        recommendations=recs,
    )
