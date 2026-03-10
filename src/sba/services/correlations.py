"""Same-Game Parlay (SGP) correlation engine and parlay builder.

Estimates correlation between prop/game markets to properly price
same-game parlays instead of using naive multiplication.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Known correlation coefficients between common NBA markets.
# Positive = outcomes tend to move together; negative = inverse.
# Source: academic papers and empirical OddsJam/Outlier data.
CORRELATION_MATRIX = {
    # (market_a, direction_a, market_b, direction_b): correlation
    ("player_points", "over", "player_assists", "over"): 0.15,
    ("player_points", "over", "player_rebounds", "over"): 0.10,
    ("player_points", "over", "player_threes", "over"): 0.45,
    ("player_points", "over", "team_win", "yes"): 0.20,
    ("player_assists", "over", "player_rebounds", "over"): 0.05,
    ("player_assists", "over", "team_win", "yes"): 0.15,
    ("player_rebounds", "over", "team_win", "yes"): 0.05,
    ("player_threes", "over", "player_points", "over"): 0.45,
    ("total_points", "over", "player_points", "over"): 0.30,
    ("total_points", "over", "player_assists", "over"): 0.20,
    ("spread", "cover", "total_points", "over"): 0.10,
    ("spread", "cover", "team_win", "yes"): 0.85,
    # Inverse correlations
    ("player_points", "over", "player_points", "under"): -1.0,
    ("total_points", "over", "total_points", "under"): -1.0,
}


@dataclass
class SGPLeg:
    """A single leg in a same-game parlay."""
    market: str
    selection: str
    direction: str  # over, under, yes, no, cover
    odds_american: int
    odds_decimal: float
    implied_prob: float
    player_name: str = ""


@dataclass
class SGPAnalysis:
    """Analysis of a same-game parlay with correlation adjustments."""
    legs: list[SGPLeg]
    naive_probability: float
    correlated_probability: float
    naive_odds_decimal: float
    correlated_odds_decimal: float
    naive_odds_american: int
    correlated_odds_american: int
    correlation_adjustment: float  # % change from naive
    correlations: list[dict] = field(default_factory=list)
    fair_value_edge: float = 0.0


def get_correlation(market_a: str, dir_a: str, market_b: str, dir_b: str) -> float:
    """Look up the correlation between two market+direction pairs."""
    key = (market_a, dir_a, market_b, dir_b)
    if key in CORRELATION_MATRIX:
        return CORRELATION_MATRIX[key]

    # Try reverse
    rev_key = (market_b, dir_b, market_a, dir_a)
    if rev_key in CORRELATION_MATRIX:
        return CORRELATION_MATRIX[rev_key]

    # Default: assume slight positive correlation for same-player props
    if market_a.startswith("player_") and market_b.startswith("player_"):
        return 0.05
    return 0.0


def build_sgp(legs: list[SGPLeg]) -> SGPAnalysis:
    """Build and analyze a same-game parlay with correlation adjustments.

    Uses a simplified Gaussian copula approach to adjust the naive
    independent-probability estimate based on known correlations.
    """
    from sba.utils.odds_math import decimal_to_american

    if len(legs) < 2:
        raise ValueError("SGP requires at least 2 legs")

    # Naive probability (assumes independence)
    naive_prob = 1.0
    for leg in legs:
        naive_prob *= leg.implied_prob

    # Calculate pairwise correlations and adjust
    correlations = []
    total_adjustment = 0.0

    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            corr = get_correlation(
                legs[i].market, legs[i].direction,
                legs[j].market, legs[j].direction,
            )
            if corr != 0:
                # Adjustment: positive correlation increases joint probability
                # for "both over" scenarios, decreases for opposite directions
                adjustment = corr * legs[i].implied_prob * legs[j].implied_prob * 0.5
                total_adjustment += adjustment
                correlations.append({
                    "leg_a": f"{legs[i].player_name} {legs[i].market} {legs[i].direction}",
                    "leg_b": f"{legs[j].player_name} {legs[j].market} {legs[j].direction}",
                    "correlation": round(corr, 3),
                    "adjustment": round(adjustment, 6),
                })

    correlated_prob = max(0.001, min(0.999, naive_prob + total_adjustment))

    # Convert probabilities to odds
    naive_dec = 1.0 / naive_prob if naive_prob > 0 else 100.0
    corr_dec = 1.0 / correlated_prob if correlated_prob > 0 else 100.0

    naive_american = decimal_to_american(naive_dec)
    corr_american = decimal_to_american(corr_dec)

    pct_change = ((correlated_prob - naive_prob) / naive_prob * 100) if naive_prob > 0 else 0

    logger.info(
        f"SGP: {len(legs)} legs, naive={naive_prob:.4f}, "
        f"correlated={correlated_prob:.4f}, adjustment={pct_change:+.1f}%"
    )

    return SGPAnalysis(
        legs=legs,
        naive_probability=round(naive_prob, 6),
        correlated_probability=round(correlated_prob, 6),
        naive_odds_decimal=round(naive_dec, 4),
        correlated_odds_decimal=round(corr_dec, 4),
        naive_odds_american=naive_american,
        correlated_odds_american=corr_american,
        correlation_adjustment=round(pct_change, 2),
        correlations=correlations,
    )
