"""Consensus probability calculations from multiple bookmakers."""

from __future__ import annotations

from sba.models.domain import BookmakerOdds
from sba.utils.odds_math import remove_vig


def consensus_probability(bookmaker_odds: list[BookmakerOdds]) -> dict[str, float]:
    """Average vig-free probabilities across all bookmakers for a given market."""
    if not bookmaker_odds:
        return {}

    outcome_probs: dict[str, list[float]] = {}

    for bm in bookmaker_odds:
        outcomes_data = [{"price_decimal": o.price_decimal} for o in bm.outcomes]
        fair_probs = remove_vig(outcomes_data)

        for outcome, prob in zip(bm.outcomes, fair_probs):
            outcome_probs.setdefault(outcome.name, []).append(prob)

    return {name: sum(probs) / len(probs) for name, probs in outcome_probs.items()}


def sharp_probability(bookmaker_odds: list[BookmakerOdds],
                      sharp_books: list[str]) -> dict[str, float]:
    """Use only sharp bookmaker lines for fair probability."""
    sharp = [bm for bm in bookmaker_odds if bm.bookmaker in sharp_books]
    if not sharp:
        return consensus_probability(bookmaker_odds)
    return consensus_probability(sharp)
