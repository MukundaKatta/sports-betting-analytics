"""Multi-method devigging engine.

Like Outlier Pro: supports multiple vig-removal methods (multiplicative,
additive, power/Shin, worst-case) with custom book weighting for
true fair odds calculation.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from sba.utils.odds_math import (
    american_to_decimal,
    decimal_to_american,
    decimal_to_implied_prob,
)

logger = logging.getLogger(__name__)

# Sharp books get higher weight by default
SHARP_BOOK_WEIGHTS: dict[str, float] = {
    "pinnacle": 1.0,
    "circa": 0.95,
    "bookmaker": 0.90,
    "betcris": 0.85,
    "bet365": 0.70,
    "draftkings": 0.60,
    "fanduel": 0.60,
    "mgm": 0.55,
    "caesars": 0.50,
}


@dataclass
class DevigResult:
    """Result of a single devig calculation."""
    method: str
    fair_probabilities: list[float]
    fair_odds_decimal: list[float]
    fair_odds_american: list[int]
    vig_removed: float
    outcome_names: list[str] = field(default_factory=list)


@dataclass
class MultiDevigResult:
    """Result of multi-method devigging with optional book weighting."""
    outcomes: list[str]
    methods: list[DevigResult]
    weighted_fair_probs: list[float]
    weighted_fair_american: list[int]
    weighted_fair_decimal: list[float]
    consensus_vig: float
    best_method: str
    books_used: list[str] = field(default_factory=list)


def devig_multiplicative(implied_probs: list[float]) -> list[float]:
    """Standard multiplicative method — divide each prob by the total."""
    total = sum(implied_probs)
    if total == 0:
        return implied_probs
    return [p / total for p in implied_probs]


def devig_additive(implied_probs: list[float]) -> list[float]:
    """Additive method — subtract equal vig from each outcome."""
    total = sum(implied_probs)
    n = len(implied_probs)
    if n == 0 or total == 0:
        return implied_probs
    excess = (total - 1.0) / n
    fair = [max(0.001, p - excess) for p in implied_probs]
    # Renormalize
    s = sum(fair)
    return [p / s for p in fair]


def devig_power(implied_probs: list[float]) -> list[float]:
    """Power method (Shin-like) — find exponent k such that sum(p^k) = 1.

    More accurately models how bookmakers set margins by applying
    a power transformation to the true probabilities.
    """
    if len(implied_probs) < 2:
        return implied_probs

    # Binary search for k
    lo, hi = 0.5, 2.0
    for _ in range(50):
        k = (lo + hi) / 2
        total = sum(p ** k for p in implied_probs)
        if total > 1.0:
            lo = k
        else:
            hi = k

    k = (lo + hi) / 2
    fair = [p ** k for p in implied_probs]
    s = sum(fair)
    return [p / s for p in fair]


def devig_worst_case(implied_probs: list[float]) -> list[float]:
    """Worst-case method — assumes maximum vig on the favorite.

    Conservative estimate: assigns more vig to the shorter-priced outcome.
    Useful for +EV calculations where you want to be cautious.
    """
    total = sum(implied_probs)
    if total <= 1.0 or len(implied_probs) < 2:
        return devig_multiplicative(implied_probs)

    excess = total - 1.0
    # Distribute vig proportional to probability squared (heavier on favorites)
    weights = [p ** 2 for p in implied_probs]
    w_total = sum(weights)
    if w_total == 0:
        return devig_multiplicative(implied_probs)

    fair = [max(0.001, p - excess * (w / w_total)) for p, w in zip(implied_probs, weights)]
    s = sum(fair)
    return [p / s for p in fair]


DEVIG_METHODS = {
    "multiplicative": devig_multiplicative,
    "additive": devig_additive,
    "power": devig_power,
    "worst_case": devig_worst_case,
}


def devig_single(
    odds_american: list[int],
    method: str = "multiplicative",
    outcome_names: list[str] | None = None,
) -> DevigResult:
    """Devig a set of odds using a single method."""
    if method not in DEVIG_METHODS:
        raise ValueError(f"Unknown method: {method}. Use: {list(DEVIG_METHODS.keys())}")

    decimals = [american_to_decimal(o) for o in odds_american]
    implied = [decimal_to_implied_prob(d) for d in decimals]
    vig = sum(implied) - 1.0

    fair_probs = DEVIG_METHODS[method](implied)
    fair_dec = [1.0 / p if p > 0 else 100.0 for p in fair_probs]
    fair_am = [decimal_to_american(d) for d in fair_dec]

    names = outcome_names or [f"outcome_{i}" for i in range(len(odds_american))]

    return DevigResult(
        method=method,
        fair_probabilities=fair_probs,
        fair_odds_decimal=[round(d, 4) for d in fair_dec],
        fair_odds_american=fair_am,
        vig_removed=round(vig * 100, 2),
        outcome_names=names,
    )


def devig_multi(
    book_odds: list[dict],
    methods: list[str] | None = None,
    method_weights: dict[str, float] | None = None,
    outcome_names: list[str] | None = None,
) -> MultiDevigResult:
    """Multi-book, multi-method devigging like Outlier Pro.

    Args:
        book_odds: List of {"bookmaker": str, "odds": [int, int, ...]}
        methods: Methods to use (default: all)
        method_weights: Weight per method for final consensus
        outcome_names: Names for each outcome
    """
    if not book_odds:
        raise ValueError("No book odds provided")

    methods = methods or list(DEVIG_METHODS.keys())
    method_weights = method_weights or {m: 1.0 for m in methods}

    num_outcomes = len(book_odds[0]["odds"])
    names = outcome_names or [f"outcome_{i}" for i in range(num_outcomes)]

    # Weight books by sharpness
    weighted_implied: list[float] = [0.0] * num_outcomes
    total_weight = 0.0

    for book in book_odds:
        bk = book["bookmaker"].lower()
        weight = SHARP_BOOK_WEIGHTS.get(bk, 0.50)
        decimals = [american_to_decimal(o) for o in book["odds"]]
        implied = [decimal_to_implied_prob(d) for d in decimals]

        for i in range(num_outcomes):
            weighted_implied[i] += implied[i] * weight
        total_weight += weight

    if total_weight > 0:
        weighted_implied = [p / total_weight for p in weighted_implied]

    # Run each devig method on the weighted implied probs
    method_results: list[DevigResult] = []
    all_fair_probs: list[list[float]] = []

    for method_name in methods:
        if method_name not in DEVIG_METHODS:
            continue
        fair_probs = DEVIG_METHODS[method_name](weighted_implied)
        fair_dec = [1.0 / p if p > 0 else 100.0 for p in fair_probs]
        fair_am = [decimal_to_american(d) for d in fair_dec]
        vig = sum(weighted_implied) - 1.0

        result = DevigResult(
            method=method_name,
            fair_probabilities=[round(p, 6) for p in fair_probs],
            fair_odds_decimal=[round(d, 4) for d in fair_dec],
            fair_odds_american=fair_am,
            vig_removed=round(vig * 100, 2),
            outcome_names=names,
        )
        method_results.append(result)
        all_fair_probs.append(fair_probs)

    # Weighted average across methods
    final_probs = [0.0] * num_outcomes
    total_mw = 0.0
    for probs, mr in zip(all_fair_probs, method_results):
        mw = method_weights.get(mr.method, 1.0)
        for i in range(num_outcomes):
            final_probs[i] += probs[i] * mw
        total_mw += mw

    if total_mw > 0:
        final_probs = [p / total_mw for p in final_probs]

    final_dec = [1.0 / p if p > 0 else 100.0 for p in final_probs]
    final_am = [decimal_to_american(d) for d in final_dec]

    # Best method = worst_case for conservative, multiplicative for standard
    best = "worst_case" if "worst_case" in methods else methods[0]

    return MultiDevigResult(
        outcomes=names,
        methods=method_results,
        weighted_fair_probs=[round(p, 6) for p in final_probs],
        weighted_fair_american=final_am,
        weighted_fair_decimal=[round(d, 4) for d in final_dec],
        consensus_vig=round((sum(weighted_implied) - 1.0) * 100, 2),
        best_method=best,
        books_used=[b["bookmaker"] for b in book_odds],
    )
