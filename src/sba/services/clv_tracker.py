"""CLV (Closing Line Value) tracking dashboard service.

CLV is the single most important metric for measuring betting skill.
Studies show bettors with consistent positive CLV achieve 2-3x higher ROI.
Inspired by Betstamp's automatic CLV measurement system.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class CLVResult:
    """CLV calculation for a single bet."""
    bet_id: int
    opening_odds: int  # American odds when bet was placed
    closing_odds: int  # American odds at game start
    clv_american: int  # Difference in American odds
    clv_percentage: float  # CLV as a percentage edge
    beat_close: bool  # Whether bettor got better odds than closing


def calculate_clv(opening_odds_american: int, closing_odds_american: int) -> dict:
    """Calculate CLV between opening and closing odds.

    CLV measures whether you consistently get better prices than the
    closing line — the most efficient predictor of long-term profitability.
    """
    open_prob = _american_to_implied(opening_odds_american)
    close_prob = _american_to_implied(closing_odds_american)

    # CLV% = (closing_prob / opening_prob - 1) * 100
    # Positive means you beat the closing line
    clv_pct = (close_prob / open_prob - 1) * 100 if open_prob > 0 else 0

    return {
        "opening_odds": opening_odds_american,
        "closing_odds": closing_odds_american,
        "opening_implied": round(open_prob * 100, 2),
        "closing_implied": round(close_prob * 100, 2),
        "clv_percentage": round(clv_pct, 2),
        "clv_american": closing_odds_american - opening_odds_american,
        "beat_close": clv_pct > 0,
        "edge_assessment": _assess_clv(clv_pct),
    }


def analyze_clv_history(clv_records: list[dict]) -> dict:
    """Analyze CLV performance across betting history.

    Returns comprehensive CLV metrics like Betstamp provides.
    """
    if not clv_records:
        return {
            "total_bets_tracked": 0,
            "avg_clv_pct": 0,
            "median_clv_pct": 0,
            "beat_close_rate": 0,
            "positive_clv_bets": 0,
            "negative_clv_bets": 0,
            "best_clv": 0,
            "worst_clv": 0,
            "by_market": {},
            "by_bookmaker": {},
            "rolling_clv": [],
            "assessment": "No CLV data available",
        }

    clv_values = [r.get("clv_percentage", 0) for r in clv_records]
    positive = [v for v in clv_values if v > 0]
    negative = [v for v in clv_values if v <= 0]

    avg_clv = sum(clv_values) / len(clv_values)
    sorted_clv = sorted(clv_values)
    median_clv = sorted_clv[len(sorted_clv) // 2]
    beat_rate = len(positive) / len(clv_values) * 100

    # By market breakdown
    by_market = {}
    by_bookmaker = {}
    for r in clv_records:
        market = r.get("market", "unknown")
        by_market.setdefault(market, []).append(r.get("clv_percentage", 0))
        book = r.get("bookmaker", "unknown")
        by_bookmaker.setdefault(book, []).append(r.get("clv_percentage", 0))

    market_summary = {}
    for m, values in by_market.items():
        market_summary[m] = {
            "avg_clv": round(sum(values) / len(values), 2),
            "count": len(values),
            "beat_rate": round(sum(1 for v in values if v > 0) / len(values) * 100, 1),
        }

    book_summary = {}
    for b, values in by_bookmaker.items():
        book_summary[b] = {
            "avg_clv": round(sum(values) / len(values), 2),
            "count": len(values),
            "beat_rate": round(sum(1 for v in values if v > 0) / len(values) * 100, 1),
        }

    # Rolling 20-bet CLV average
    rolling = []
    window = 20
    for i in range(len(clv_values)):
        start = max(0, i - window + 1)
        window_vals = clv_values[start:i + 1]
        rolling.append({
            "bet_number": i + 1,
            "clv": round(clv_values[i], 2),
            "rolling_avg": round(sum(window_vals) / len(window_vals), 2),
        })

    # Overall assessment
    if avg_clv > 3 and beat_rate > 60:
        assessment = "Elite — You are consistently beating closing lines. Strong evidence of a real edge."
    elif avg_clv > 1 and beat_rate > 55:
        assessment = "Sharp — Positive CLV trend suggests genuine skill. Continue current approach."
    elif avg_clv > 0:
        assessment = "Promising — Slight positive CLV. Sample size may be too small for confidence."
    elif avg_clv > -2:
        assessment = "Neutral — CLV near breakeven. Focus on improving line shopping and timing."
    else:
        assessment = "Concerning — Negative CLV suggests you may be getting worse prices than the market. Prioritize line shopping."

    return {
        "total_bets_tracked": len(clv_records),
        "avg_clv_pct": round(avg_clv, 2),
        "median_clv_pct": round(median_clv, 2),
        "beat_close_rate": round(beat_rate, 1),
        "positive_clv_bets": len(positive),
        "negative_clv_bets": len(negative),
        "best_clv": round(max(clv_values), 2),
        "worst_clv": round(min(clv_values), 2),
        "by_market": market_summary,
        "by_bookmaker": book_summary,
        "rolling_clv": rolling,
        "assessment": assessment,
    }


def _american_to_implied(odds: int) -> float:
    """Convert American odds to implied probability."""
    if odds > 0:
        return 100 / (odds + 100)
    elif odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 0.5


def _assess_clv(clv_pct: float) -> str:
    """Assess a single CLV reading."""
    if clv_pct > 5:
        return "Excellent value captured"
    elif clv_pct > 2:
        return "Strong positive CLV"
    elif clv_pct > 0:
        return "Beat the closing line"
    elif clv_pct > -2:
        return "Close to closing line"
    else:
        return "Worse price than closing line"
