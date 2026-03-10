"""Multi-strategy staking system.

Implements advanced bankroll management strategies used by professional bettors.
Inspired by Bet-Analytix and BetMetrics Lab — the leading staking tools.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class StakeRecommendation:
    """Result of a staking calculation."""
    strategy: str
    stake: float
    unit_size: float
    bankroll: float
    reasoning: str


def flat_stake(bankroll: float, unit_pct: float = 2.0) -> StakeRecommendation:
    """Fixed percentage of bankroll per bet."""
    stake = bankroll * (unit_pct / 100)
    return StakeRecommendation(
        strategy="flat",
        stake=round(stake, 2),
        unit_size=unit_pct,
        bankroll=bankroll,
        reasoning=f"Fixed {unit_pct}% of ${bankroll:,.2f} bankroll",
    )


def kelly_criterion(bankroll: float, odds_decimal: float,
                    win_prob: float, fraction: float = 0.25) -> StakeRecommendation:
    """Kelly Criterion with configurable fraction.

    Args:
        bankroll: Current bankroll
        odds_decimal: Decimal odds (e.g. 2.0 for even money)
        win_prob: Estimated probability of winning (0-1)
        fraction: Kelly fraction (0.25 = quarter Kelly, recommended for most bettors)
    """
    b = odds_decimal - 1  # net odds received
    q = 1 - win_prob
    full_kelly = (b * win_prob - q) / b if b > 0 else 0
    full_kelly = max(0, full_kelly)

    adjusted = full_kelly * fraction
    stake = bankroll * adjusted

    label = {0.25: "Quarter", 0.5: "Half", 1.0: "Full"}.get(fraction, f"{fraction:.0%}")

    return StakeRecommendation(
        strategy="kelly",
        stake=round(stake, 2),
        unit_size=round(adjusted * 100, 2),
        bankroll=bankroll,
        reasoning=f"{label} Kelly: {adjusted*100:.2f}% of bankroll "
                  f"(full Kelly = {full_kelly*100:.2f}%, edge = {(win_prob * odds_decimal - 1)*100:.1f}%)",
    )


def percentage_bankroll(bankroll: float, confidence: str = "medium") -> StakeRecommendation:
    """Confidence-based percentage staking.

    Uses tiered percentages based on confidence level, similar to how
    Action Network and Pikkit categorize bet confidence.
    """
    pct_map = {
        "low": 1.0,
        "medium": 2.0,
        "high": 3.0,
        "max": 5.0,
    }
    pct = pct_map.get(confidence, 2.0)
    stake = bankroll * (pct / 100)

    return StakeRecommendation(
        strategy="percentage",
        stake=round(stake, 2),
        unit_size=pct,
        bankroll=bankroll,
        reasoning=f"{confidence.title()} confidence: {pct}% of bankroll",
    )


def fibonacci_recovery(bankroll: float, loss_streak: int,
                       base_unit: float | None = None) -> StakeRecommendation:
    """Fibonacci progression for recovery after losses.

    Uses Fibonacci sequence for stake sizing during losing streaks.
    More conservative than Martingale while still accelerating recovery.
    """
    if base_unit is None:
        base_unit = bankroll * 0.01  # 1% base unit

    # Fibonacci sequence
    def fib(n: int) -> int:
        if n <= 0:
            return 1
        a, b = 1, 1
        for _ in range(n):
            a, b = b, a + b
        return a

    multiplier = fib(min(loss_streak, 10))  # cap at fib(10) = 89
    stake = base_unit * multiplier
    # Cap at 5% of bankroll for safety
    stake = min(stake, bankroll * 0.05)

    return StakeRecommendation(
        strategy="fibonacci",
        stake=round(stake, 2),
        unit_size=round(stake / bankroll * 100, 2) if bankroll > 0 else 0,
        bankroll=bankroll,
        reasoning=f"Fibonacci level {loss_streak}: {multiplier}x base unit "
                  f"(${base_unit:.2f}), capped at 5% bankroll",
    )


def proportional_ev(bankroll: float, ev_pct: float,
                    max_pct: float = 5.0) -> StakeRecommendation:
    """Stake proportional to expected value edge.

    Higher EV bets get larger allocations. Used by sharp bettors
    to maximize edge exploitation.
    """
    # Scale: 1% EV = 1% bankroll, 5% EV = 3% bankroll, 10% EV = 5% bankroll
    if ev_pct <= 0:
        stake_pct = 0
    else:
        stake_pct = min(max_pct, ev_pct * 0.5)

    stake = bankroll * (stake_pct / 100)

    return StakeRecommendation(
        strategy="proportional_ev",
        stake=round(stake, 2),
        unit_size=round(stake_pct, 2),
        bankroll=bankroll,
        reasoning=f"EV-proportional: {ev_pct:.1f}% EV → {stake_pct:.2f}% stake",
    )


def compare_strategies(bankroll: float, odds_decimal: float = 2.0,
                       win_prob: float = 0.55, ev_pct: float = 5.0,
                       confidence: str = "medium",
                       loss_streak: int = 0) -> list[dict]:
    """Compare all staking strategies side by side.

    Returns a list of recommendations from each strategy for easy comparison.
    """
    results = [
        flat_stake(bankroll),
        kelly_criterion(bankroll, odds_decimal, win_prob, 0.25),
        kelly_criterion(bankroll, odds_decimal, win_prob, 0.5),
        percentage_bankroll(bankroll, confidence),
        proportional_ev(bankroll, ev_pct),
    ]

    if loss_streak > 0:
        results.append(fibonacci_recovery(bankroll, loss_streak))

    return [
        {
            "strategy": r.strategy,
            "stake": r.stake,
            "unit_pct": r.unit_size,
            "bankroll": r.bankroll,
            "reasoning": r.reasoning,
        }
        for r in results
    ]
