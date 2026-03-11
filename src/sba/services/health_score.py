"""Betting Health Score — a composite metric that evaluates overall betting quality.

Inspired by credit scores but for sports betting. Combines:
- CLV performance (are you beating closing lines?)
- ROI sustainability (are returns consistent, not just lucky?)
- Bankroll management discipline (proper sizing, no tilt?)
- Edge detection accuracy (how often do model edges hit?)
- Risk diversification (exposure spread across books/events/markets)

Score range: 0–100 (Poor / Fair / Good / Excellent / Elite)
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from sba.data.db import get_connection

logger = logging.getLogger(__name__)


def calculate_health_score() -> dict:
    """Calculate the composite Betting Health Score with component breakdown."""
    with get_connection() as conn:
        bets = conn.execute("""
            SELECT b.*, e.sport
            FROM bets b LEFT JOIN events e ON e.id = b.event_id
            WHERE b.status IN ('won', 'lost', 'push')
            ORDER BY b.placed_at
        """).fetchall()

        clv_rows = conn.execute("""
            SELECT cl.*, b.odds_american AS placed_odds
            FROM closing_lines cl JOIN bets b ON cl.bet_id = b.id
        """).fetchall()

        bankroll_log = conn.execute(
            "SELECT * FROM bankroll_log ORDER BY created_at DESC LIMIT 90"
        ).fetchall()

    if len(bets) < 10:
        return {
            "score": None,
            "grade": "N/A",
            "message": "Need at least 10 settled bets to calculate health score.",
            "components": {},
            "sample_size": len(bets),
        }

    components = {
        "clv": _score_clv(clv_rows),
        "roi": _score_roi(bets),
        "discipline": _score_discipline(bets),
        "accuracy": _score_accuracy(bets),
        "diversification": _score_diversification(bets),
    }

    # Weighted composite score
    weights = {"clv": 0.25, "roi": 0.25, "discipline": 0.20, "accuracy": 0.15, "diversification": 0.15}
    composite = sum(components[k]["score"] * weights[k] for k in weights)
    composite = round(min(100, max(0, composite)), 1)

    grade = _score_to_grade(composite)

    return {
        "score": composite,
        "grade": grade,
        "message": _grade_message(grade),
        "components": components,
        "sample_size": len(bets),
        "last_updated": datetime.now().isoformat(),
        "recommendations": _generate_recommendations(components),
    }


def _score_clv(clv_rows) -> dict:
    """Score CLV performance (0-100). Beating closing lines is the gold standard."""
    if not clv_rows:
        return {"score": 50, "label": "Closing Line Value", "detail": "No CLV data tracked yet"}

    beat_count = sum(1 for r in clv_rows if (r["clv_percentage"] or 0) > 0)
    beat_pct = beat_count / len(clv_rows) * 100
    avg_clv = sum(r["clv_percentage"] or 0 for r in clv_rows) / len(clv_rows)

    # 50% beat rate = 50 score, 60% = 80, 70% = 100
    score = min(100, max(0, (beat_pct - 40) * 2.5))
    # Boost for strong average CLV
    if avg_clv > 2:
        score = min(100, score + 10)

    return {
        "score": round(score),
        "label": "Closing Line Value",
        "beat_pct": round(beat_pct, 1),
        "avg_clv": round(avg_clv, 2),
        "tracked": len(clv_rows),
        "detail": f"Beating closing {beat_pct:.0f}% of the time (avg CLV: {avg_clv:+.1f}%)",
    }


def _score_roi(bets) -> dict:
    """Score ROI sustainability (0-100). Consistent profits > lucky streak."""
    total_profit = sum(b["profit_loss"] or 0 for b in bets)
    total_staked = sum(abs(b["recommended_stake"] or 0) for b in bets) or 1
    roi = total_profit / total_staked * 100

    # Calculate rolling 30-bet windows for consistency
    window = 30
    if len(bets) >= window:
        windows = []
        for i in range(0, len(bets) - window + 1, window // 2):
            chunk = bets[i:i + window]
            w_profit = sum(b["profit_loss"] or 0 for b in chunk)
            w_staked = sum(abs(b["recommended_stake"] or 0) for b in chunk) or 1
            windows.append(w_profit / w_staked * 100)

        # Consistency: low standard deviation of rolling ROI
        if len(windows) >= 2:
            mean_w = sum(windows) / len(windows)
            variance = sum((w - mean_w) ** 2 for w in windows) / len(windows)
            std_dev = math.sqrt(variance)
            consistency = max(0, 100 - std_dev * 5)  # Lower volatility = higher score
        else:
            consistency = 50
    else:
        consistency = 50

    # ROI score: -5% = 0, 0% = 40, 5% = 70, 10% = 90, 15%+ = 100
    roi_score = min(100, max(0, 40 + roi * 6))
    score = roi_score * 0.6 + consistency * 0.4

    return {
        "score": round(score),
        "label": "ROI Sustainability",
        "roi_pct": round(roi, 2),
        "total_profit": round(total_profit, 2),
        "consistency": round(consistency, 1),
        "detail": f"ROI: {roi:+.1f}% across {len(bets)} bets",
    }


def _score_discipline(bets) -> dict:
    """Score bankroll management discipline (0-100)."""
    stakes = [abs(b["recommended_stake"] or 0) for b in bets if b["recommended_stake"]]
    if not stakes:
        return {"score": 50, "label": "Bankroll Discipline", "detail": "No stake data"}

    avg_stake = sum(stakes) / len(stakes)
    max_stake = max(stakes)

    # Check for consistency in stake sizing
    if avg_stake > 0:
        variance = sum((s - avg_stake) ** 2 for s in stakes) / len(stakes)
        cv = math.sqrt(variance) / avg_stake  # Coefficient of variation
    else:
        cv = 1.0

    # Deductions for chasing (big stakes after losses)
    chase_count = 0
    for i in range(1, len(bets)):
        prev = bets[i - 1]
        curr = bets[i]
        if prev["status"] == "lost" and (curr["recommended_stake"] or 0) > avg_stake * 1.5:
            chase_count += 1

    chase_rate = chase_count / max(len(bets) - 1, 1) * 100

    # Low CV = consistent = good. CV > 1 = chaotic
    consistency_score = max(0, 100 - cv * 40)
    chase_penalty = chase_rate * 3
    score = max(0, consistency_score - chase_penalty)

    return {
        "score": round(score),
        "label": "Bankroll Discipline",
        "avg_stake": round(avg_stake, 2),
        "max_stake": round(max_stake, 2),
        "stake_cv": round(cv, 3),
        "chase_rate": round(chase_rate, 1),
        "detail": f"Stake consistency: {consistency_score:.0f}/100, chase rate: {chase_rate:.0f}%",
    }


def _score_accuracy(bets) -> dict:
    """Score edge detection accuracy (0-100)."""
    total = len(bets)
    won = sum(1 for b in bets if b["status"] == "won")
    win_rate = won / total * 100

    # Check if high-EV bets hit at a higher rate
    high_ev_bets = [b for b in bets if (b["expected_value"] or 0) > 5]
    if high_ev_bets:
        high_ev_wins = sum(1 for b in high_ev_bets if b["status"] == "won")
        high_ev_wr = high_ev_wins / len(high_ev_bets) * 100
    else:
        high_ev_wr = win_rate

    # Score: 45% wr = 30, 50% = 50, 55% = 70, 60% = 90
    base_score = min(100, max(0, (win_rate - 35) * 2.5))
    # Bonus if high EV bets outperform
    ev_bonus = min(20, max(0, (high_ev_wr - win_rate) * 2))
    score = min(100, base_score + ev_bonus)

    return {
        "score": round(score),
        "label": "Edge Accuracy",
        "win_rate": round(win_rate, 1),
        "high_ev_win_rate": round(high_ev_wr, 1),
        "total_bets": total,
        "detail": f"Win rate: {win_rate:.1f}% ({won}/{total})",
    }


def _score_diversification(bets) -> dict:
    """Score risk diversification (0-100)."""
    books = set()
    markets = set()
    sports = set()

    for b in bets:
        if b["bookmaker"]:
            books.add(b["bookmaker"])
        if b["market"]:
            markets.add(b["market"])
        sport = b["sport"] if "sport" in b.keys() else None
        if sport:
            sports.add(sport)

    # Score based on breadth of coverage
    book_score = min(40, len(books) * 8)  # Up to 5 books = 40
    market_score = min(30, len(markets) * 10)  # Up to 3 markets = 30
    sport_score = min(30, len(sports) * 10)  # Up to 3 sports = 30
    score = book_score + market_score + sport_score

    return {
        "score": round(score),
        "label": "Diversification",
        "unique_books": len(books),
        "unique_markets": len(markets),
        "unique_sports": len(sports),
        "detail": f"{len(books)} books, {len(markets)} markets, {len(sports)} sports",
    }


def _score_to_grade(score: float) -> str:
    if score >= 90:
        return "Elite"
    elif score >= 75:
        return "Excellent"
    elif score >= 60:
        return "Good"
    elif score >= 40:
        return "Fair"
    else:
        return "Poor"


def _grade_message(grade: str) -> str:
    messages = {
        "Elite": "Your betting fundamentals are exceptional. You're consistently beating the market.",
        "Excellent": "Strong performance across all metrics. Keep executing your strategy.",
        "Good": "Solid foundation with room for improvement in a few areas.",
        "Fair": "Some areas need attention. Review the recommendations below.",
        "Poor": "Significant improvements needed. Focus on discipline and edge quality.",
    }
    return messages.get(grade, "")


def _generate_recommendations(components: dict) -> list[dict]:
    """Generate actionable recommendations based on component scores."""
    recs = []

    clv = components.get("clv", {})
    if clv.get("score", 100) < 50:
        recs.append({
            "priority": "high",
            "area": "CLV",
            "action": "Focus on getting bets placed earlier when lines first open. "
                      "Sharp books like Pinnacle set fair lines — use them as your benchmark.",
        })

    roi = components.get("roi", {})
    if roi.get("consistency", 100) < 40:
        recs.append({
            "priority": "high",
            "area": "Consistency",
            "action": "Your results are volatile. Consider reducing variance by using "
                      "fractional Kelly (quarter-Kelly) and avoiding large favorites.",
        })

    discipline = components.get("discipline", {})
    if discipline.get("chase_rate", 0) > 10:
        recs.append({
            "priority": "high",
            "area": "Tilt Control",
            "action": "You're increasing stakes after losses (chasing). Set a hard rule: "
                      "never increase bet size after a loss. Consider a 24-hour cooling period.",
        })

    accuracy = components.get("accuracy", {})
    if accuracy.get("score", 100) < 50:
        recs.append({
            "priority": "medium",
            "area": "Edge Quality",
            "action": "Your hit rate is below optimal. Consider raising your minimum EV "
                      "threshold to 3%+ and focusing on markets with more data.",
        })

    div = components.get("diversification", {})
    if div.get("score", 100) < 40:
        recs.append({
            "priority": "medium",
            "area": "Diversification",
            "action": "You're concentrated in too few books/markets. Spread across more "
                      "sportsbooks to access the best lines and reduce account limiting risk.",
        })

    if not recs:
        recs.append({
            "priority": "info",
            "area": "Keep It Up",
            "action": "All metrics are strong. Maintain your current strategy and discipline.",
        })

    return recs
