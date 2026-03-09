"""Odds format conversions and probability calculations."""

from __future__ import annotations


def american_to_decimal(american: int) -> float:
    if american > 0:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def decimal_to_american(decimal: float) -> int:
    if decimal >= 2.0:
        return round((decimal - 1.0) * 100)
    return round(-100.0 / (decimal - 1.0))


def american_to_implied_prob(american: int) -> float:
    if american > 0:
        return 100.0 / (american + 100.0)
    return abs(american) / (abs(american) + 100.0)


def decimal_to_implied_prob(decimal: float) -> float:
    if decimal <= 0:
        return 0.0
    return 1.0 / decimal


def remove_vig(outcomes: list[dict]) -> list[float]:
    """Remove vig using multiplicative method. Returns fair probabilities.

    Each outcome dict must have 'price_decimal' key.
    """
    implied_probs = [decimal_to_implied_prob(o["price_decimal"]) for o in outcomes]
    total = sum(implied_probs)
    if total == 0:
        return implied_probs
    return [p / total for p in implied_probs]


def calculate_vig(outcomes: list[dict]) -> float:
    """Calculate the total overround (vig) percentage."""
    implied_probs = [decimal_to_implied_prob(o["price_decimal"]) for o in outcomes]
    return sum(implied_probs) - 1.0
