"""Expected-value math for betting edge finders.

Pure helpers the edge-finder calls for every book / market / outcome
combination: implied probability from American/Decimal/Fractional odds,
removing the book's overround to get the implicit fair probability,
expected value of a wager, and Kelly-fraction sizing with configurable
fractional-Kelly safety. All deterministic and dependency-free.

**Educational.** Not betting advice; not a solicitation to place bets.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Sequence


def decimal_to_prob(decimal_odds: float) -> float:
    if decimal_odds <= 1:
        return 1.0
    return 1.0 / decimal_odds


def american_to_decimal(american: int) -> float:
    if american == 0:
        return 1.0
    if american > 0:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def american_to_prob(american: int) -> float:
    return decimal_to_prob(american_to_decimal(american))


def fractional_to_decimal(num: int, den: int) -> float:
    if den == 0:
        return 1.0
    return 1.0 + num / den


def remove_overround(implied_probs: Sequence[float]) -> list[float]:
    """Normalise a set of implied probabilities so they sum to 1."""
    total = sum(implied_probs)
    if total <= 0:
        return [0.0 for _ in implied_probs]
    return [p / total for p in implied_probs]


def book_overround(implied_probs: Sequence[float]) -> float:
    """The vig expressed as a fraction over 1 (0.05 = 5% vig)."""
    return max(0.0, sum(implied_probs) - 1.0)


@dataclass(frozen=True)
class Wager:
    decimal_odds: float
    true_prob: float      # analyst's estimated fair probability
    stake: float = 1.0


@dataclass(frozen=True)
class EvResult:
    expected_value: float       # per unit stake
    edge: float                 # true prob minus implied prob
    roi: float                  # ev / stake
    positive: bool


def expected_value(wager: Wager) -> EvResult:
    """EV over a single wager."""
    implied = decimal_to_prob(wager.decimal_odds)
    win = (wager.decimal_odds - 1.0) * wager.stake
    ev = wager.true_prob * win - (1.0 - wager.true_prob) * wager.stake
    roi = ev / wager.stake if wager.stake else 0.0
    return EvResult(
        expected_value=round(ev, 4),
        edge=round(wager.true_prob - implied, 4),
        roi=round(roi, 4),
        positive=ev > 0,
    )


def kelly_fraction(
    decimal_odds: float,
    true_prob: float,
    *,
    fractional: float = 0.25,
    cap: float = 0.05,
) -> float:
    """Kelly-optimal stake as a fraction of bankroll.

    `fractional` scales the raw Kelly down — standard practice for
    bankroll survival. `cap` is a hard ceiling on stake-per-bet so a
    single wager can't eat more than that fraction of bankroll even if
    the edge looks huge.
    """
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - true_prob
    raw = (b * true_prob - q) / b
    if raw <= 0:
        return 0.0
    return round(min(cap, raw * fractional), 4)


def log_growth_rate(decimal_odds: float, true_prob: float, bankroll_fraction: float) -> float:
    """Expected log-bankroll growth per bet at a given bankroll fraction."""
    b = decimal_odds - 1.0
    up = 1.0 + bankroll_fraction * b
    down = 1.0 - bankroll_fraction
    if up <= 0 or down <= 0:
        return float("-inf")
    return true_prob * log(up) + (1.0 - true_prob) * log(down)
