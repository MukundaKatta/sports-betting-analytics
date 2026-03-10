"""Kelly criterion for optimal bet sizing."""


def full_kelly(prob: float, odds_decimal: float) -> float:
    """Full Kelly criterion. Returns fraction of bankroll to wager.

    Formula: (p * b - q) / b  where b = odds - 1, q = 1 - p
    """
    if odds_decimal <= 1.0 or prob <= 0 or prob >= 1:
        return 0.0
    b = odds_decimal - 1.0
    q = 1.0 - prob
    kelly = (prob * b - q) / b
    return max(0.0, kelly)


def fractional_kelly(prob: float, odds_decimal: float, fraction: float = 0.25) -> float:
    """Fractional Kelly — reduces variance at cost of slightly lower growth.

    Quarter-Kelly (0.25) is standard for sports betting.
    """
    if odds_decimal <= 1.0:
        return 0.0
    return full_kelly(prob, odds_decimal) * fraction


def kelly_stake(prob: float, odds_decimal: float, bankroll: float,
                fraction: float = 0.25) -> float:
    """Dollar amount to wager using fractional Kelly."""
    if odds_decimal <= 1.0:
        return 0.0
    pct = fractional_kelly(prob, odds_decimal, fraction)
    return round(bankroll * pct, 2)
