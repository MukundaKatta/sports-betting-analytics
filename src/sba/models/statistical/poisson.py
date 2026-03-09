"""Poisson model for game totals and score predictions."""

from __future__ import annotations

import math
from functools import lru_cache


def poisson_prob(k: int, lam: float) -> float:
    """Probability of exactly k events given expected rate lambda."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    # Use log-space to avoid overflow for large k
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))


def over_under_prob(total_line: float, home_lambda: float,
                    away_lambda: float, max_score: int = 200) -> tuple[float, float]:
    """Calculate over/under probabilities using joint Poisson distribution.

    For high-scoring sports like basketball, uses normal approximation
    when combined lambda > 50.
    """
    combined_lambda = home_lambda + away_lambda

    # Normal approximation for high-scoring games (NBA, etc.)
    if combined_lambda > 50:
        import math
        mean = combined_lambda
        std = math.sqrt(combined_lambda)
        # P(X > line) using normal CDF approximation
        z = (total_line - mean) / std
        over_p = 1.0 - _normal_cdf(z)
        under_p = _normal_cdf(z)
        return (over_p, under_p)

    # Exact Poisson for lower-scoring games (soccer, hockey)
    # Cap max_score based on lambda to avoid wasted computation
    effective_max = min(max_score, int(max(home_lambda, away_lambda) * 5) + 10)
    over_p = 0.0
    under_p = 0.0

    for h in range(effective_max + 1):
        for a in range(effective_max + 1):
            p = poisson_prob(h, home_lambda) * poisson_prob(a, away_lambda)
            total = h + a
            if total > total_line:
                over_p += p
            elif total < total_line:
                under_p += p
            # Exact push is excluded (neither over nor under)

    return (over_p, under_p)


def moneyline_from_poisson(home_lambda: float, away_lambda: float,
                           max_score: int = 10) -> tuple[float, float, float]:
    """Derive moneyline probabilities from Poisson score matrix.

    Returns: (home_win_prob, draw_prob, away_win_prob)
    """
    home_win = 0.0
    draw = 0.0
    away_win = 0.0

    for h in range(max_score + 1):
        for a in range(max_score + 1):
            p = poisson_prob(h, home_lambda) * poisson_prob(a, away_lambda)
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p

    return (home_win, draw, away_win)


def _normal_cdf(z: float) -> float:
    """Approximation of the standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))
