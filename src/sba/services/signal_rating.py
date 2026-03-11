"""Unified signal rating system — traffic light + confidence scoring.

Combines edge data, sharp agreement, pattern matches, and ML predictions
into a simple traffic light signal (green/yellow/red) with a 0-100
confidence score. Inspired by Outlier's traffic light system and
BetQL's star ratings.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SignalRating:
    """A unified signal rating for a betting opportunity."""
    signal: str  # "green", "yellow", "red"
    confidence: int  # 0-100
    stars: int  # 1-5
    label: str  # "Strong Play", "Lean", "Avoid"
    reasons: list[str]
    warnings: list[str]


def rate_opportunity(
    ev_pct: float = 0.0,
    edge_pct: float | None = None,
    sharp_agrees: bool = False,
    line_moving_toward: bool = False,
    line_moving_away: bool = False,
    pattern_confidence: float | None = None,
    pattern_roi: float | None = None,
    ml_probability: float | None = None,
    books_with_edge: int = 1,
    total_books: int = 1,
    odds_american: int = 0,
    is_live: bool = False,
) -> SignalRating:
    """Rate a betting opportunity with traffic light + confidence score.

    Inputs can come from edge finder, smart signals, or manual analysis.
    All parameters are optional — the system works with whatever data
    is available, adjusting confidence based on data completeness.
    """
    edge = edge_pct if edge_pct is not None else ev_pct * 100
    score = 0
    reasons = []
    warnings = []
    data_points = 0

    # 1. Edge/EV (up to 45 points — primary factor)
    if edge > 0:
        edge_score = min(45, edge * 6)
        score += edge_score
        data_points += 1
        if edge >= 8:
            reasons.append(f"Exceptional {edge:.1f}% edge")
        elif edge >= 5:
            reasons.append(f"Strong {edge:.1f}% edge")
        elif edge >= 3:
            reasons.append(f"Solid {edge:.1f}% edge")
        elif edge >= 1:
            reasons.append(f"Small {edge:.1f}% edge")

    # 2. Sharp agreement (up to 20 points)
    if sharp_agrees:
        score += 20
        data_points += 1
        reasons.append("Sharp books agree")

    # 3. Line movement (up to 15 points)
    if line_moving_toward:
        score += 15
        data_points += 1
        reasons.append("Confirming line movement")
    elif line_moving_away:
        score -= 5
        data_points += 1
        warnings.append("Line moving against this side")
        if sharp_agrees:
            score += 10  # Reverse line movement is strong signal
            reasons.append("Reverse line movement (sharp vs public)")

    # 4. Pattern match (up to 15 points)
    if pattern_confidence is not None and pattern_confidence > 0:
        pattern_score = min(15, pattern_confidence / 100 * 15)
        score += pattern_score
        data_points += 1
        if pattern_roi and pattern_roi > 10:
            reasons.append(f"Pattern match: {pattern_roi:.0f}% historical ROI")
        elif pattern_confidence >= 60:
            reasons.append("Matches a profitable pattern")

    # 5. ML prediction (up to 10 points)
    if ml_probability is not None:
        ml_score = min(10, (ml_probability - 0.5) * 40)
        if ml_score > 0:
            score += ml_score
            data_points += 1
            reasons.append(f"ML model: {ml_probability*100:.0f}% probability")

    # 6. Market breadth (up to 5 points)
    if books_with_edge > 1 and total_books > 1:
        breadth = books_with_edge / total_books
        score += min(5, breadth * 10)
        reasons.append(f"Edge at {books_with_edge}/{total_books} books")
    elif total_books >= 5 and books_with_edge <= 1:
        warnings.append("Edge only at 1 book — possible stale line")

    # Penalties
    if is_live:
        score *= 0.8
        warnings.append("Live market — higher uncertainty")

    # Data completeness note (no score penalty — edge alone is a valid signal)
    if data_points < 2:
        warnings.append("Limited confirming data — consider waiting for more signals")

    score = max(0, min(100, score))

    # Determine signal
    if score >= 50:
        signal = "green"
        label = "Strong Play"
    elif score >= 15:
        signal = "yellow"
        label = "Lean"
    else:
        signal = "red"
        label = "Avoid"

    # Stars (1-5)
    if score >= 70:
        stars = 5
    elif score >= 50:
        stars = 4
    elif score >= 30:
        stars = 3
    elif score >= 15:
        stars = 2
    else:
        stars = 1

    if not reasons:
        reasons.append("Insufficient data for strong signal")

    return SignalRating(
        signal=signal,
        confidence=round(score),
        stars=stars,
        label=label,
        reasons=reasons,
        warnings=warnings,
    )
