"""Arbitrage and middle betting detection engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sba.models.domain import EventOdds, Outcome
from sba.utils.odds_math import american_to_decimal, decimal_to_implied_prob

logger = logging.getLogger(__name__)


@dataclass
class ArbOpportunity:
    """A guaranteed-profit arbitrage opportunity."""

    event_home: str
    event_away: str
    event_id: str
    market: str
    outcome_a: str
    outcome_b: str
    book_a: str
    book_b: str
    odds_a_american: int
    odds_b_american: int
    odds_a_decimal: float
    odds_b_decimal: float
    total_implied: float
    profit_pct: float
    stake_a_pct: float
    stake_b_pct: float


@dataclass
class MiddleOpportunity:
    """A middle betting opportunity where both sides can win."""

    event_home: str
    event_away: str
    event_id: str
    market: str
    selection: str
    book_a: str
    book_b: str
    line_a: float
    line_b: float
    odds_a_american: int
    odds_b_american: int
    gap: float
    description: str


@dataclass
class LowHoldMarket:
    """A market with very low vig / hold percentage."""

    event_home: str
    event_away: str
    event_id: str
    market: str
    best_book_a: str
    best_book_b: str
    best_odds_a_american: int
    best_odds_b_american: int
    hold_pct: float


def find_arbitrage(events_odds: list[EventOdds]) -> list[ArbOpportunity]:
    """Scan events for two-way arbitrage opportunities.

    An arb exists when the sum of the best implied probabilities
    across books is less than 1.0 (i.e. total overround < 0).
    """
    arbs = []

    for eo in events_odds:
        markets = _group_by_market(eo)

        for market, bm_list in markets.items():
            outcomes = _get_best_odds_per_outcome(bm_list)
            outcome_names = list(outcomes.keys())

            if len(outcome_names) < 2:
                continue

            # Check all pairs for two-way arb
            for i in range(len(outcome_names)):
                for j in range(i + 1, len(outcome_names)):
                    name_a = outcome_names[i]
                    name_b = outcome_names[j]
                    best_a = outcomes[name_a]
                    best_b = outcomes[name_b]

                    imp_a = decimal_to_implied_prob(best_a["odds"].price_decimal)
                    imp_b = decimal_to_implied_prob(best_b["odds"].price_decimal)
                    total = imp_a + imp_b

                    if total < 1.0:
                        profit_pct = (1.0 / total - 1.0) * 100
                        stake_a_pct = imp_a / total * 100
                        stake_b_pct = imp_b / total * 100

                        arbs.append(ArbOpportunity(
                            event_home=eo.event.home_team,
                            event_away=eo.event.away_team,
                            event_id=eo.event.id,
                            market=market,
                            outcome_a=name_a,
                            outcome_b=name_b,
                            book_a=best_a["bookmaker"],
                            book_b=best_b["bookmaker"],
                            odds_a_american=best_a["odds"].price_american,
                            odds_b_american=best_b["odds"].price_american,
                            odds_a_decimal=best_a["odds"].price_decimal,
                            odds_b_decimal=best_b["odds"].price_decimal,
                            total_implied=round(total, 4),
                            profit_pct=round(profit_pct, 2),
                            stake_a_pct=round(stake_a_pct, 1),
                            stake_b_pct=round(stake_b_pct, 1),
                        ))

    arbs.sort(key=lambda x: x.profit_pct, reverse=True)
    logger.info(f"Found {len(arbs)} arbitrage opportunities")
    return arbs


def find_middles(events_odds: list[EventOdds]) -> list[MiddleOpportunity]:
    """Find middle opportunities on spreads and totals.

    A middle exists when you can bet both sides with different
    lines that create a gap where both bets can win.
    """
    middles = []

    for eo in events_odds:
        markets = _group_by_market(eo)

        for market in ("spreads", "totals"):
            bm_list = markets.get(market, [])
            if not bm_list:
                continue

            # Group outcomes by name (selection)
            by_selection: dict[str, list[tuple[str, Outcome]]] = {}
            for bm in bm_list:
                for outcome in bm.outcomes:
                    by_selection.setdefault(outcome.name, []).append(
                        (bm.bookmaker, outcome)
                    )

            # For each selection, find line differences across books
            for selection, book_outcomes in by_selection.items():
                if len(book_outcomes) < 2:
                    continue

                # Sort by line (point)
                with_lines = [(bk, o) for bk, o in book_outcomes if o.point is not None]
                if not with_lines:
                    continue

                lines = sorted(with_lines, key=lambda x: x[1].point)
                low_bk, low_o = lines[0]
                high_bk, high_o = lines[-1]

                if low_o.point != high_o.point and low_bk != high_bk:
                    gap = abs(high_o.point - low_o.point)
                    if gap >= 0.5:
                        if market == "totals":
                            desc = f"Over {low_o.point} / Under {high_o.point} = {gap} point window"
                        else:
                            desc = f"{selection} {low_o.point} / {high_o.point} = {gap} point middle"

                        middles.append(MiddleOpportunity(
                            event_home=eo.event.home_team,
                            event_away=eo.event.away_team,
                            event_id=eo.event.id,
                            market=market,
                            selection=selection,
                            book_a=low_bk,
                            book_b=high_bk,
                            line_a=low_o.point,
                            line_b=high_o.point,
                            odds_a_american=low_o.price_american,
                            odds_b_american=high_o.price_american,
                            gap=gap,
                            description=desc,
                        ))

    middles.sort(key=lambda x: x.gap, reverse=True)
    logger.info(f"Found {len(middles)} middle opportunities")
    return middles


def find_low_holds(events_odds: list[EventOdds], max_hold: float = 0.03) -> list[LowHoldMarket]:
    """Find markets with low hold/vig percentage.

    Useful for bonus rollover optimization where you want to minimize
    the expected loss from vig.
    """
    low_holds = []

    for eo in events_odds:
        markets = _group_by_market(eo)

        for market, bm_list in markets.items():
            outcomes = _get_best_odds_per_outcome(bm_list)
            if len(outcomes) < 2:
                continue

            # Use best odds from any book to compute the lowest possible hold
            total_implied = sum(
                decimal_to_implied_prob(v["odds"].price_decimal)
                for v in outcomes.values()
            )
            hold = total_implied - 1.0

            if hold <= max_hold:
                outcome_list = list(outcomes.values())
                low_holds.append(LowHoldMarket(
                    event_home=eo.event.home_team,
                    event_away=eo.event.away_team,
                    event_id=eo.event.id,
                    market=market,
                    best_book_a=outcome_list[0]["bookmaker"],
                    best_book_b=outcome_list[1]["bookmaker"] if len(outcome_list) > 1 else outcome_list[0]["bookmaker"],
                    best_odds_a_american=outcome_list[0]["odds"].price_american,
                    best_odds_b_american=outcome_list[1]["odds"].price_american if len(outcome_list) > 1 else 0,
                    hold_pct=round(hold * 100, 2),
                ))

    low_holds.sort(key=lambda x: x.hold_pct)
    logger.info(f"Found {len(low_holds)} low-hold markets (≤{max_hold*100}%)")
    return low_holds


def _group_by_market(event_odds: EventOdds) -> dict:
    """Group bookmaker odds by market type."""
    markets = {}
    for bm in event_odds.bookmakers:
        markets.setdefault(bm.market, []).append(bm)
    return markets


def _get_best_odds_per_outcome(bm_list) -> dict[str, dict]:
    """For each outcome, find the best available odds across all books."""
    best: dict[str, dict] = {}
    for bm in bm_list:
        for outcome in bm.outcomes:
            key = outcome.name
            if key not in best or outcome.price_decimal > best[key]["odds"].price_decimal:
                best[key] = {"odds": outcome, "bookmaker": bm.bookmaker}
    return best
