"""Streak detection and momentum analytics service.

Identifies hot/cold streaks, calculates momentum scores,
and provides actionable signals based on betting patterns.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime

from sba.data.db import get_connection

logger = logging.getLogger(__name__)


@dataclass
class StreakInfo:
    streak_type: str  # "win", "loss", "mixed"
    length: int
    profit: float
    roi_pct: float
    avg_odds: int
    started_at: str | None = None


@dataclass
class MomentumScore:
    score: float  # -100 to +100
    label: str  # "Hot", "Warm", "Neutral", "Cold", "Ice Cold"
    signal: str  # "increase_stakes", "hold_steady", "reduce_stakes", "take_a_break"
    reasoning: list[str]


def get_streak_analysis() -> dict:
    """Analyze current and historical streaks from bet history."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT status, profit_loss, odds_american, recommended_stake,
                   market, bookmaker, placed_at
            FROM bets WHERE status IN ('won', 'lost', 'push')
            ORDER BY placed_at DESC
        """).fetchall()

    if not rows:
        return {
            "current_streak": {"type": "none", "length": 0, "profit": 0},
            "streaks_today": [],
            "momentum": {"score": 0, "label": "Neutral", "signal": "hold_steady", "reasoning": []},
            "historical_streaks": {"longest_win": 0, "longest_loss": 0, "avg_win_streak": 0},
        }

    # Current streak
    current_type = rows[0]["status"]
    current_length = 0
    current_profit = 0.0
    current_odds_sum = 0

    for r in rows:
        if r["status"] == current_type:
            current_length += 1
            current_profit += r["profit_loss"] or 0
            current_odds_sum += r["odds_american"] or 0
        else:
            break

    current_streak = StreakInfo(
        streak_type=current_type,
        length=current_length,
        profit=round(current_profit, 2),
        roi_pct=round(current_profit / max(abs(current_profit) + 1, 1) * 100, 1),
        avg_odds=round(current_odds_sum / max(current_length, 1)),
        started_at=rows[min(current_length - 1, len(rows) - 1)]["placed_at"],
    )

    # All streaks
    streaks: list[StreakInfo] = []
    i = 0
    while i < len(rows):
        stype = rows[i]["status"]
        slen = 0
        sprof = 0.0
        sodds = 0
        start = rows[i]["placed_at"]
        while i < len(rows) and rows[i]["status"] == stype:
            slen += 1
            sprof += rows[i]["profit_loss"] or 0
            sodds += rows[i]["odds_american"] or 0
            i += 1
        streaks.append(StreakInfo(
            streak_type=stype, length=slen,
            profit=round(sprof, 2),
            roi_pct=round(sprof / max(abs(sprof) + 1, 1) * 100, 1),
            avg_odds=round(sodds / max(slen, 1)),
            started_at=start,
        ))

    win_streaks = [s for s in streaks if s.streak_type == "won"]
    loss_streaks = [s for s in streaks if s.streak_type == "lost"]

    # Momentum score calculation
    momentum = _calculate_momentum(rows)

    return {
        "current_streak": {
            "type": current_streak.streak_type,
            "length": current_streak.length,
            "profit": current_streak.profit,
            "avg_odds": current_streak.avg_odds,
            "started_at": current_streak.started_at,
        },
        "momentum": {
            "score": momentum.score,
            "label": momentum.label,
            "signal": momentum.signal,
            "reasoning": momentum.reasoning,
        },
        "historical_streaks": {
            "longest_win": max((s.length for s in win_streaks), default=0),
            "longest_loss": max((s.length for s in loss_streaks), default=0),
            "avg_win_streak": round(
                sum(s.length for s in win_streaks) / max(len(win_streaks), 1), 1
            ),
            "avg_loss_streak": round(
                sum(s.length for s in loss_streaks) / max(len(loss_streaks), 1), 1
            ),
            "total_streaks": len(streaks),
        },
        "recent_streaks": [
            {
                "type": s.streak_type, "length": s.length,
                "profit": s.profit, "avg_odds": s.avg_odds,
            }
            for s in streaks[:10]
        ],
    }


def _calculate_momentum(rows: list) -> MomentumScore:
    """Calculate momentum score from -100 to +100.

    Factors:
    - Recent results (last 5, 10, 20 bets with recency weighting)
    - ROI trend (improving or declining)
    - Consistency (variance in results)
    """
    if not rows:
        return MomentumScore(0, "Neutral", "hold_steady", [])

    reasoning = []

    # Factor 1: Weighted recent results (last 20, more weight on recent)
    recent = rows[:min(20, len(rows))]
    weighted_score = 0
    total_weight = 0
    for i, r in enumerate(recent):
        weight = 1.0 / (1 + i * 0.15)  # exponential decay
        total_weight += weight
        if r["status"] == "won":
            weighted_score += weight
        elif r["status"] == "lost":
            weighted_score -= weight
        # push = 0

    recency_factor = (weighted_score / total_weight) * 50  # scale to -50 to +50

    # Factor 2: ROI of last 10 vs last 20
    last_10 = rows[:min(10, len(rows))]
    last_20 = rows[:min(20, len(rows))]

    pnl_10 = sum(r["profit_loss"] or 0 for r in last_10)
    stake_10 = sum(abs(r["recommended_stake"] or 0) for r in last_10) or 1
    roi_10 = pnl_10 / stake_10 * 100

    pnl_20 = sum(r["profit_loss"] or 0 for r in last_20)
    stake_20 = sum(abs(r["recommended_stake"] or 0) for r in last_20) or 1
    roi_20 = pnl_20 / stake_20 * 100

    trend_factor = min(25, max(-25, (roi_10 - roi_20) * 2))

    if roi_10 > roi_20 + 5:
        reasoning.append(f"ROI trending up: {roi_10:.1f}% (L10) vs {roi_20:.1f}% (L20)")
    elif roi_10 < roi_20 - 5:
        reasoning.append(f"ROI trending down: {roi_10:.1f}% (L10) vs {roi_20:.1f}% (L20)")

    # Factor 3: Win rate last 5
    last_5 = rows[:min(5, len(rows))]
    wins_5 = sum(1 for r in last_5 if r["status"] == "won")
    wr_5 = wins_5 / len(last_5) * 100
    consistency_factor = min(25, max(-25, (wr_5 - 50) * 0.5))

    if wr_5 >= 80:
        reasoning.append(f"Hot streak: {wins_5}/{len(last_5)} wins in last 5")
    elif wr_5 <= 20:
        reasoning.append(f"Cold streak: {wins_5}/{len(last_5)} wins in last 5")

    # Combine factors
    raw_score = recency_factor + trend_factor + consistency_factor
    score = round(max(-100, min(100, raw_score)), 1)

    # Determine label and signal
    if score >= 50:
        label, signal = "Hot", "hold_steady"
        reasoning.append("Strong positive momentum — maintain current approach")
    elif score >= 20:
        label, signal = "Warm", "hold_steady"
        reasoning.append("Positive momentum — stay disciplined")
    elif score >= -20:
        label, signal = "Neutral", "hold_steady"
        reasoning.append("Neutral momentum — stick to your strategy")
    elif score >= -50:
        label, signal = "Cold", "reduce_stakes"
        reasoning.append("Negative momentum — consider reducing stake sizes")
    else:
        label, signal = "Ice Cold", "take_a_break"
        reasoning.append("Severe negative momentum — review strategy before continuing")

    return MomentumScore(score=score, label=label, signal=signal, reasoning=reasoning)


def get_daily_summary() -> dict:
    """Generate a smart daily summary of betting activity and recommendations."""
    from datetime import date

    today = date.today().isoformat()

    with get_connection() as conn:
        # Today's results
        today_rows = conn.execute("""
            SELECT status, profit_loss, market, bookmaker, odds_american,
                   recommended_stake, selection
            FROM bets WHERE DATE(placed_at) = ?
            ORDER BY placed_at DESC
        """, (today,)).fetchall()

        # Yesterday comparison
        yesterday = (date.today() - __import__('datetime').timedelta(days=1)).isoformat()
        yesterday_rows = conn.execute("""
            SELECT status, profit_loss FROM bets
            WHERE DATE(placed_at) = ? AND status IN ('won', 'lost', 'push')
        """, (yesterday,)).fetchall()

        # This week
        week_rows = conn.execute("""
            SELECT status, profit_loss, recommended_stake FROM bets
            WHERE placed_at >= DATE('now', '-7 days')
              AND status IN ('won', 'lost', 'push')
        """).fetchall()

        # Bankroll
        bankroll_row = conn.execute(
            "SELECT amount FROM bankroll_log ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

        # Pending bets count
        pending = conn.execute(
            "SELECT COUNT(*) as cnt FROM bets WHERE status = 'pending'"
        ).fetchone()

        # Best performing market this week
        best_market = conn.execute("""
            SELECT market,
                   COUNT(*) as bets,
                   ROUND(SUM(profit_loss), 2) as profit,
                   ROUND(SUM(CASE WHEN status='won' THEN 1.0 ELSE 0.0 END) / COUNT(*) * 100, 1) as wr
            FROM bets
            WHERE placed_at >= DATE('now', '-7 days') AND status IN ('won', 'lost', 'push')
            GROUP BY market ORDER BY profit DESC LIMIT 1
        """).fetchone()

    # Calculate today's stats
    settled_today = [r for r in today_rows if r["status"] in ("won", "lost", "push")]
    today_profit = sum(r["profit_loss"] or 0 for r in settled_today)
    today_wins = sum(1 for r in settled_today if r["status"] == "won")
    today_bets = len(settled_today)
    today_pending = sum(1 for r in today_rows if r["status"] == "pending")

    # Yesterday comparison
    yesterday_profit = sum(r["profit_loss"] or 0 for r in yesterday_rows)

    # Week stats
    week_profit = sum(r["profit_loss"] or 0 for r in week_rows)
    week_staked = sum(abs(r["recommended_stake"] or 0) for r in week_rows) or 1
    week_roi = round(week_profit / week_staked * 100, 1)
    week_wr = round(
        sum(1 for r in week_rows if r["status"] == "won") / max(len(week_rows), 1) * 100, 1
    )

    # Generate smart insights
    insights = []
    if today_profit > 0:
        insights.append(f"Profitable day: +${today_profit:.2f}")
    elif today_profit < 0:
        insights.append(f"Down ${abs(today_profit):.2f} today — review bet sizing")
    if today_profit > yesterday_profit:
        insights.append("Performing better than yesterday")
    if week_roi > 5:
        insights.append(f"Strong week with {week_roi}% ROI")
    elif week_roi < -5:
        insights.append(f"Challenging week at {week_roi}% ROI — stay disciplined")
    if best_market:
        insights.append(f"Best market: {best_market['market']} ({best_market['profit']})")

    return {
        "date": today,
        "today": {
            "bets": today_bets,
            "wins": today_wins,
            "pending": today_pending,
            "profit": round(today_profit, 2),
            "win_rate": round(today_wins / max(today_bets, 1) * 100, 1),
        },
        "yesterday_profit": round(yesterday_profit, 2),
        "week": {
            "bets": len(week_rows),
            "profit": round(week_profit, 2),
            "roi": week_roi,
            "win_rate": week_wr,
        },
        "bankroll": round(bankroll_row["amount"], 2) if bankroll_row else 0,
        "pending_bets": pending["cnt"] if pending else 0,
        "best_market": {
            "market": best_market["market"],
            "profit": best_market["profit"],
            "win_rate": best_market["wr"],
        } if best_market else None,
        "insights": insights,
    }
