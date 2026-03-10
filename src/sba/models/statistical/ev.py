"""Expected value calculations."""

from __future__ import annotations

from sba.config import get_settings
from sba.models.domain import EdgeOpportunity, EventOdds, Outcome
from sba.models.statistical.kelly import fractional_kelly, kelly_stake
from sba.utils.odds_math import decimal_to_implied_prob


def calculate_ev(model_prob: float, odds_decimal: float) -> float:
    """Calculate expected value as fraction of stake.

    Returns: EV per unit staked. E.g., 0.05 means +5% edge.
    """
    return (model_prob * (odds_decimal - 1)) - (1 - model_prob)


def best_available_odds(event_odds: EventOdds, market: str,
                        outcome_name: str) -> tuple[str, Outcome] | None:
    """Find the best price across all bookmakers for a specific outcome."""
    best_book = None
    best_outcome = None

    for bm in event_odds.bookmakers:
        if bm.market != market:
            continue
        for o in bm.outcomes:
            if o.name == outcome_name:
                if best_outcome is None or o.price_decimal > best_outcome.price_decimal:
                    best_outcome = o
                    best_book = bm.bookmaker

    if best_book and best_outcome:
        return (best_book, best_outcome)
    return None


def find_ev_opportunities(event_odds: EventOdds,
                          model_probs: dict[str, float],
                          market: str = "h2h",
                          threshold: float | None = None) -> list[EdgeOpportunity]:
    """Compare model probabilities against each bookmaker's line.

    Returns opportunities where EV exceeds threshold.
    """
    settings = get_settings()
    if threshold is None:
        threshold = settings.EV_THRESHOLD

    opportunities = []

    for outcome_name, model_prob in model_probs.items():
        result = best_available_odds(event_odds, market, outcome_name)
        if not result:
            continue

        book, odds = result
        ev = calculate_ev(model_prob, odds.price_decimal)

        if ev >= threshold:
            kelly_pct = fractional_kelly(model_prob, odds.price_decimal, settings.KELLY_FRACTION)
            stake = kelly_stake(model_prob, odds.price_decimal,
                                settings.BANKROLL, settings.KELLY_FRACTION)

            confidence = "low"
            if ev >= 0.08:
                confidence = "high"
            elif ev >= 0.04:
                confidence = "medium"

            implied = decimal_to_implied_prob(odds.price_decimal)

            opportunities.append(EdgeOpportunity(
                event=event_odds.event,
                market=market,
                selection=outcome_name,
                line=odds.point,
                best_odds=odds,
                bookmaker=book,
                model_prob=model_prob,
                implied_prob=implied,
                ev=ev,
                kelly_pct=kelly_pct,
                recommended_stake=stake,
                confidence=confidence,
            ))

    opportunities.sort(key=lambda x: x.ev, reverse=True)
    return opportunities
