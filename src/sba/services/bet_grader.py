"""Bet grading and rating system.

Like BetQL's 1-5 star rating system: rates every bet opportunity based on
edge size, sharp agreement, line movement direction, historical hit rate,
and market efficiency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Thresholds for star ratings
STAR_THRESHOLDS = {
    5: 8.0,   # 8%+ edge = 5 stars
    4: 5.0,   # 5-8% = 4 stars
    3: 3.0,   # 3-5% = 3 stars
    2: 1.5,   # 1.5-3% = 2 stars
    1: 0.0,   # 0-1.5% = 1 star
}


@dataclass
class BetGrade:
    """A graded bet opportunity with star rating and breakdown."""
    selection: str
    market: str
    event: str
    stars: int  # 1-5
    overall_score: float  # 0-100
    edge_pct: float
    confidence: str  # "low", "medium", "high", "very_high"
    grade_label: str  # "Strong Play", "Good Value", etc.

    # Component scores (0-100 each)
    edge_score: float = 0.0
    sharp_score: float = 0.0
    movement_score: float = 0.0
    consistency_score: float = 0.0
    market_score: float = 0.0

    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def grade_bet(
    selection: str,
    market: str,
    event: str,
    edge_pct: float,
    best_odds_american: int,
    fair_odds_american: int | None = None,
    sharp_book_agrees: bool = False,
    line_moving_toward: bool = False,
    line_moving_away: bool = False,
    historical_hit_rate: float | None = None,
    books_with_edge: int = 1,
    total_books: int = 1,
    is_live: bool = False,
    hours_to_start: float | None = None,
) -> BetGrade:
    """Grade a bet opportunity on multiple dimensions.

    Returns a BetGrade with 1-5 star rating, component scores, and reasons.
    """
    reasons = []
    warnings = []

    # 1. Edge Score (0-100) — primary factor
    edge_score = min(100, edge_pct * 10)  # 10% edge = 100
    if edge_pct >= 8:
        reasons.append(f"Exceptional {edge_pct:.1f}% edge detected")
    elif edge_pct >= 5:
        reasons.append(f"Strong {edge_pct:.1f}% edge vs fair value")
    elif edge_pct >= 3:
        reasons.append(f"Solid {edge_pct:.1f}% edge")

    # 2. Sharp Agreement Score (0-100)
    sharp_score = 0.0
    if sharp_book_agrees:
        sharp_score = 80.0
        reasons.append("Sharp books agree with this side")
    if books_with_edge > 1:
        multi_book_bonus = min(20, (books_with_edge - 1) * 10)
        sharp_score = min(100, sharp_score + multi_book_bonus)
        reasons.append(f"Edge available at {books_with_edge}/{total_books} books")

    # 3. Line Movement Score (0-100)
    movement_score = 50.0  # Neutral default
    if line_moving_toward:
        movement_score = 80.0
        reasons.append("Line moving toward this side (confirming)")
    elif line_moving_away:
        movement_score = 20.0
        warnings.append("Line moving away — steam could be against you")
    # Reverse line movement (sharp money opposing public) is very strong
    if line_moving_away and sharp_book_agrees:
        movement_score = 90.0
        reasons.append("Reverse line movement + sharp agreement (strong signal)")

    # 4. Consistency Score (0-100)
    consistency_score = 50.0
    if historical_hit_rate is not None:
        consistency_score = historical_hit_rate  # Already 0-100
        if historical_hit_rate >= 60:
            reasons.append(f"Historical hit rate: {historical_hit_rate:.0f}%")
        elif historical_hit_rate < 40:
            warnings.append(f"Below-average hit rate: {historical_hit_rate:.0f}%")

    # 5. Market Efficiency Score (0-100)
    market_score = 50.0
    if is_live:
        market_score = 30.0  # Live markets are less reliable
        warnings.append("Live market — odds can shift rapidly")
    if hours_to_start is not None:
        if hours_to_start > 24:
            market_score = max(market_score, 70.0)
            reasons.append("Early line — market hasn't fully adjusted")
        elif hours_to_start < 1:
            market_score = min(market_score, 40.0)
    if total_books >= 5 and books_with_edge <= 1:
        market_score = max(20.0, market_score - 20)
        warnings.append("Only 1 book offering this edge — could be stale line")

    # Calculate overall score (weighted average)
    overall_score = (
        edge_score * 0.35
        + sharp_score * 0.25
        + movement_score * 0.15
        + consistency_score * 0.15
        + market_score * 0.10
    )

    # Determine star rating
    stars = 1
    for s, threshold in sorted(STAR_THRESHOLDS.items(), reverse=True):
        if edge_pct >= threshold:
            stars = s
            break

    # Boost/penalize stars based on other factors
    if sharp_book_agrees and stars < 5:
        stars = min(5, stars + 1)
    if line_moving_away and not sharp_book_agrees and stars > 1:
        stars = max(1, stars - 1)

    # Confidence level
    if overall_score >= 75:
        confidence = "very_high"
    elif overall_score >= 55:
        confidence = "high"
    elif overall_score >= 35:
        confidence = "medium"
    else:
        confidence = "low"

    # Grade label
    labels = {
        5: "Strong Play",
        4: "Good Value",
        3: "Solid Bet",
        2: "Marginal Edge",
        1: "Low Confidence",
    }

    return BetGrade(
        selection=selection,
        market=market,
        event=event,
        stars=stars,
        overall_score=round(overall_score, 1),
        edge_pct=round(edge_pct, 2),
        confidence=confidence,
        grade_label=labels.get(stars, "Unrated"),
        edge_score=round(edge_score, 1),
        sharp_score=round(sharp_score, 1),
        movement_score=round(movement_score, 1),
        consistency_score=round(consistency_score, 1),
        market_score=round(market_score, 1),
        reasons=reasons,
        warnings=warnings,
    )


def grade_bets_batch(bets: list[dict]) -> list[BetGrade]:
    """Grade multiple bet opportunities and sort by score."""
    grades = []
    for bet in bets:
        grade = grade_bet(**bet)
        grades.append(grade)

    grades.sort(key=lambda g: g.overall_score, reverse=True)
    return grades
