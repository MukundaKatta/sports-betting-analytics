"""Arbitrage (sure-bet) detection across bookmakers."""

from __future__ import annotations

from itertools import product

from sba.models.domain import (
    ArbOpportunity,
    ArbOutcome,
    EventOdds,
)
from sba.utils.odds_math import decimal_to_implied_prob


def _best_odds_per_outcome(
    event_odds: EventOdds,
    market: str,
) -> dict[str, tuple[str, float, int]]:
    """Find the best decimal odds for each outcome name across all bookmakers.

    Returns:
        Mapping of outcome_name -> (bookmaker, best_decimal, best_american).
    """
    best: dict[str, tuple[str, float, int]] = {}

    for bm in event_odds.bookmakers:
        if bm.market != market:
            continue
        for o in bm.outcomes:
            current = best.get(o.name)
            if current is None or o.price_decimal > current[1]:
                best[o.name] = (bm.bookmaker, o.price_decimal, o.price_american)

    return best


def calculate_stakes(
    odds_decimals: list[float],
    total_bankroll: float = 1.0,
) -> list[float]:
    """Calculate optimal stake distribution for guaranteed profit.

    Given the best decimal odds for each side, returns the dollar amount
    to place on each outcome so that the payout is equal regardless of
    which outcome wins.

    Args:
        odds_decimals: Best decimal odds for each outcome.
        total_bankroll: Total amount to distribute across all outcomes.

    Returns:
        List of stake amounts (one per outcome), summing to total_bankroll.
    """
    if not odds_decimals or any(o <= 0 for o in odds_decimals):
        return [0.0] * len(odds_decimals)

    implied = [1.0 / o for o in odds_decimals]
    total_implied = sum(implied)

    if total_implied == 0:
        return [0.0] * len(odds_decimals)

    # Each stake is proportional to 1/odds, normalised to total_bankroll
    return [total_bankroll * (ip / total_implied) for ip in implied]


def detect_arbitrage(
    event_odds: EventOdds,
    market: str,
) -> ArbOpportunity | None:
    """Detect a sure-bet arbitrage for a given event and market.

    For each distinct outcome in the market, picks the best decimal odds
    across all bookmakers. If the sum of implied probabilities is below
    1.0, an arbitrage exists.

    Handles 2-way (h2h without draw) and 3-way (h2h with draw) markets.

    Args:
        event_odds: An event with odds from multiple bookmakers.
        market: The market key, e.g. ``"h2h"``.

    Returns:
        An ``ArbOpportunity`` if an arb exists, otherwise ``None``.
    """
    best = _best_odds_per_outcome(event_odds, market)

    if len(best) < 2:
        return None

    outcome_names = sorted(best.keys())
    odds_decimals = [best[name][1] for name in outcome_names]
    implied_probs = [decimal_to_implied_prob(d) for d in odds_decimals]
    total_implied = sum(implied_probs)

    if total_implied >= 1.0:
        return None  # No arb

    profit_pct = (1.0 / total_implied - 1.0) * 100.0
    stakes = calculate_stakes(odds_decimals, total_bankroll=1.0)

    arb_outcomes: list[ArbOutcome] = []
    for name, imp, stake in zip(outcome_names, implied_probs, stakes):
        bookmaker, dec, amer = best[name]
        arb_outcomes.append(ArbOutcome(
            outcome_name=name,
            bookmaker=bookmaker,
            odds_decimal=dec,
            odds_american=amer,
            implied_prob=imp,
            stake_fraction=stake,
        ))

    return ArbOpportunity(
        event=event_odds.event,
        market=market,
        outcomes=arb_outcomes,
        total_implied_prob=total_implied,
        profit_pct=profit_pct,
        stakes=stakes,
    )


def scan_arbitrage(
    events_odds: list[EventOdds],
    markets: list[str] | None = None,
) -> list[ArbOpportunity]:
    """Scan multiple events for arbitrage opportunities.

    Args:
        events_odds: List of events with bookmaker odds.
        markets: Market keys to check. Defaults to ``["h2h"]``.

    Returns:
        List of detected arbitrage opportunities sorted by profit_pct
        (highest first).
    """
    if markets is None:
        markets = ["h2h"]

    arbs: list[ArbOpportunity] = []

    for eo in events_odds:
        for mkt in markets:
            arb = detect_arbitrage(eo, mkt)
            if arb is not None:
                arbs.append(arb)

    arbs.sort(key=lambda a: a.profit_pct, reverse=True)
    return arbs
