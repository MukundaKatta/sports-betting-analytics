"""Public betting percentages and money flow tracker.

Like Action Network PRO: tracks public bet % vs money % to detect
sharp/public divergence. When public bets one way but money goes
the other, sharps are on the opposite side.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PublicMoneyData:
    """Public betting and money split for an event outcome."""
    event_id: str
    market: str
    outcome: str
    bet_pct: float  # % of total bets on this side
    money_pct: float  # % of total money on this side
    sharp_side: bool  # True if money diverges from bets (sharp action)
    divergence: float  # money_pct - bet_pct (positive = sharp money)


@dataclass
class PublicMoneyAnalysis:
    """Complete public money analysis for an event."""
    event_id: str
    market: str
    outcomes: list[PublicMoneyData]
    sharp_signal: str | None  # Which side sharps favor, or None
    signal_strength: str  # "none", "weak", "moderate", "strong"
    description: str


def analyze_public_money(
    event_id: str,
    market: str,
    outcomes: list[dict],
) -> PublicMoneyAnalysis:
    """Analyze public betting % vs money % for an event.

    Args:
        event_id: Event identifier
        market: Market type (h2h, spreads, totals)
        outcomes: List of dicts with:
            - name: str (outcome name)
            - bet_pct: float (% of bets, 0-100)
            - money_pct: float (% of money, 0-100)
    """
    if not outcomes:
        return PublicMoneyAnalysis(
            event_id=event_id, market=market, outcomes=[],
            sharp_signal=None, signal_strength="none",
            description="No data available",
        )

    results = []
    max_divergence = 0.0
    sharp_outcome = None

    for o in outcomes:
        bet_pct = o.get("bet_pct", 50.0)
        money_pct = o.get("money_pct", 50.0)
        divergence = money_pct - bet_pct
        sharp_side = divergence > 5.0  # Money exceeds bets by >5%

        if divergence > 5 and divergence > max_divergence:
            max_divergence = divergence
            sharp_outcome = o.get("name")
        elif abs(divergence) > abs(max_divergence):
            max_divergence = divergence

        results.append(PublicMoneyData(
            event_id=event_id,
            market=market,
            outcome=o.get("name", ""),
            bet_pct=round(bet_pct, 1),
            money_pct=round(money_pct, 1),
            sharp_side=sharp_side,
            divergence=round(divergence, 1),
        ))

    # Signal strength based on divergence
    abs_div = abs(max_divergence)
    if abs_div >= 15:
        strength = "strong"
    elif abs_div >= 8:
        strength = "moderate"
    elif abs_div >= 5:
        strength = "weak"
    else:
        strength = "none"

    # Build description
    if sharp_outcome and strength != "none":
        # Find the public side
        public_side = max(results, key=lambda r: r.bet_pct)
        if public_side.outcome != sharp_outcome:
            desc = (
                f"Public is on {public_side.outcome} ({public_side.bet_pct}% of bets) "
                f"but money is on {sharp_outcome} — classic sharp/public divergence"
            )
        else:
            desc = f"Public and money both favor {sharp_outcome}"
    else:
        desc = "No significant sharp/public divergence detected"

    return PublicMoneyAnalysis(
        event_id=event_id,
        market=market,
        outcomes=results,
        sharp_signal=sharp_outcome,
        signal_strength=strength,
        description=desc,
    )


def simulate_public_money(
    event_id: str,
    home_team: str,
    away_team: str,
    home_odds_american: int,
    away_odds_american: int,
    market: str = "h2h",
) -> PublicMoneyAnalysis:
    """Generate simulated public money splits from odds movement patterns.

    Uses odds as a proxy: when odds shorten despite expected public action
    on the other side, it indicates sharp money.
    """
    from sba.utils.odds_math import american_to_implied_prob

    home_prob = american_to_implied_prob(home_odds_american)
    away_prob = american_to_implied_prob(away_odds_american)

    # Simulate: public tends to bet favorites and overs more heavily
    is_home_favorite = home_prob > away_prob

    if is_home_favorite:
        # Public typically bets ~60-65% on favorites
        home_bet_pct = min(75, 50 + (home_prob - 0.5) * 50)
        # Money is distributed more evenly (sharps balance it)
        home_money_pct = min(70, 45 + (home_prob - 0.5) * 40)
    else:
        home_bet_pct = max(25, 50 - (away_prob - 0.5) * 50)
        home_money_pct = max(30, 55 - (away_prob - 0.5) * 40)

    away_bet_pct = 100 - home_bet_pct
    away_money_pct = 100 - home_money_pct

    outcomes = [
        {"name": home_team, "bet_pct": home_bet_pct, "money_pct": home_money_pct},
        {"name": away_team, "bet_pct": away_bet_pct, "money_pct": away_money_pct},
    ]

    return analyze_public_money(event_id, market, outcomes)
