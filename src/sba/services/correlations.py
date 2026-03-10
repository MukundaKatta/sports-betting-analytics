"""Same-Game Parlay (SGP) correlation engine and parlay builder.

Estimates correlation between prop/game markets to properly price
same-game parlays instead of using naive multiplication.

v2.4: Expanded from NBA-only to NFL, MLB, NHL. Added conflict detection
and "LINKED" leg tagging inspired by EdgeSlip's correlation engine.
v2.7: Sport-aware lookup — each sport has its own correlation sub-dict,
fixing duplicate key bug where NFL overwrote NBA spread/team_win.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Multi-Sport Correlation Matrix ──────────────────────────────────
#
# Known correlation coefficients between common markets, keyed by sport.
# Positive = outcomes tend to move together; negative = inverse.
# Sources: academic papers, empirical data, EdgeSlip methodology.

_CorrelationKey = tuple[str, str, str, str]

SPORT_CORRELATIONS: dict[str, dict[_CorrelationKey, float]] = {
    "default": {
        # Universal inverse correlations
        ("player_points", "over", "player_points", "under"): -1.0,
        ("total_points", "over", "total_points", "under"): -1.0,
    },
    "nba": {
        ("player_points", "over", "player_assists", "over"): 0.15,
        ("player_points", "over", "player_rebounds", "over"): 0.10,
        ("player_points", "over", "player_threes", "over"): 0.45,
        ("player_points", "over", "team_win", "yes"): 0.20,
        ("player_assists", "over", "player_rebounds", "over"): 0.05,
        ("player_assists", "over", "team_win", "yes"): 0.15,
        ("player_rebounds", "over", "team_win", "yes"): 0.05,
        ("player_threes", "over", "player_points", "over"): 0.45,
        ("total_points", "over", "player_points", "over"): 0.30,
        ("total_points", "over", "player_assists", "over"): 0.20,
        ("spread", "cover", "total_points", "over"): 0.10,
        ("spread", "cover", "team_win", "yes"): 0.85,
        # Blowout effect: winning team's starters play fewer minutes
        ("team_win", "yes", "player_points", "under"): 0.08,
        ("player_steals", "over", "team_win", "yes"): 0.12,
        ("player_blocks", "over", "player_rebounds", "over"): 0.20,
    },
    "nfl": {
        ("qb_passing_yards", "over", "qb_passing_tds", "over"): 0.55,
        ("qb_passing_yards", "over", "wr_receiving_yards", "over"): 0.50,
        ("qb_passing_tds", "over", "wr_receiving_yards", "over"): 0.40,
        ("qb_passing_yards", "over", "total_points", "over"): 0.35,
        ("rb_rushing_yards", "over", "team_win", "yes"): 0.20,
        ("rb_rushing_yards", "over", "total_points", "under"): 0.10,
        ("wr_receiving_yards", "over", "wr_receptions", "over"): 0.65,
        ("wr_receiving_yards", "over", "wr_anytime_td", "yes"): 0.30,
        ("qb_interceptions", "over", "team_win", "no"): 0.35,
        ("total_points", "over", "qb_passing_yards", "over"): 0.35,
        ("spread", "cover", "team_win", "yes"): 0.90,
        ("qb_passing_yards", "over", "qb_interceptions", "over"): 0.15,
        ("rb_rushing_yards", "over", "rb_rushing_tds", "over"): 0.40,
    },
    "mlb": {
        ("pitcher_strikeouts", "over", "total_runs", "under"): 0.25,
        ("pitcher_strikeouts", "over", "team_win", "yes"): 0.20,
        ("batter_hits", "over", "batter_rbis", "over"): 0.35,
        ("batter_hits", "over", "batter_runs", "over"): 0.30,
        ("total_runs", "over", "batter_hits", "over"): 0.25,
        ("batter_home_runs", "over", "batter_rbis", "over"): 0.50,
        ("batter_home_runs", "over", "total_runs", "over"): 0.20,
    },
    "nhl": {
        ("player_goals", "over", "player_shots", "over"): 0.40,
        ("player_goals", "over", "player_points_nhl", "over"): 0.70,
        ("player_assists_nhl", "over", "player_points_nhl", "over"): 0.65,
        ("player_shots", "over", "team_win", "yes"): 0.10,
        ("total_goals", "over", "player_goals", "over"): 0.25,
        ("goalie_saves", "over", "total_goals", "under"): -0.15,
    },
}

# Backward-compatible flat view (merged, last-write-wins as before)
CORRELATION_MATRIX: dict[_CorrelationKey, float] = {}
for _sport_pairs in SPORT_CORRELATIONS.values():
    CORRELATION_MATRIX.update(_sport_pairs)

# ── Sport key normalization ────────────────────────────────────────
_SPORT_ALIASES: dict[str, str] = {
    "basketball_nba": "nba",
    "americanfootball_nfl": "nfl",
    "baseball_mlb": "mlb",
    "icehockey_nhl": "nhl",
}


def normalize_sport(sport_key: str) -> str:
    """Map API sport keys (e.g. 'basketball_nba') to short form ('nba')."""
    lower = sport_key.lower()
    return _SPORT_ALIASES.get(lower, lower)

# ── Conflict Rules (invalid leg combinations) ──────────────────────
# These pairs cannot coexist in the same SGP.
CONFLICT_PAIRS = [
    ("player_points", "over", "player_points", "under"),
    ("total_points", "over", "total_points", "under"),
    ("team_win", "yes", "team_win", "no"),
    ("spread", "cover", "spread", "not_cover"),
    ("total_goals", "over", "total_goals", "under"),
    ("total_runs", "over", "total_runs", "under"),
]


@dataclass
class SGPLeg:
    """A single leg in a same-game parlay."""
    market: str
    selection: str
    direction: str  # over, under, yes, no, cover
    odds_american: int
    odds_decimal: float
    implied_prob: float
    player_name: str = ""


@dataclass
class SGPAnalysis:
    """Analysis of a same-game parlay with correlation adjustments."""
    legs: list[SGPLeg]
    naive_probability: float
    correlated_probability: float
    naive_odds_decimal: float
    correlated_odds_decimal: float
    naive_odds_american: int
    correlated_odds_american: int
    correlation_adjustment: float  # % change from naive
    correlations: list[dict] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    fair_value_edge: float = 0.0


def get_correlation(
    market_a: str, dir_a: str, market_b: str, dir_b: str,
    sport: str = "nba",
) -> float:
    """Look up the correlation between two market+direction pairs.

    Args:
        sport: Short sport key ('nba', 'nfl', 'mlb', 'nhl') or API key
               ('basketball_nba'). Defaults to 'nba' for backward compat.
    """
    sport = normalize_sport(sport)
    key = (market_a, dir_a, market_b, dir_b)
    rev_key = (market_b, dir_b, market_a, dir_a)

    # 1. Sport-specific lookup
    sport_dict = SPORT_CORRELATIONS.get(sport, {})
    if key in sport_dict:
        return sport_dict[key]
    if rev_key in sport_dict:
        return sport_dict[rev_key]

    # 2. Default (universal) correlations
    defaults = SPORT_CORRELATIONS.get("default", {})
    if key in defaults:
        return defaults[key]
    if rev_key in defaults:
        return defaults[rev_key]

    # 3. Heuristic: slight positive correlation for same-player props
    if market_a.startswith("player_") and market_b.startswith("player_"):
        return 0.05
    return 0.0


def check_conflicts(legs: list[SGPLeg]) -> list[str]:
    """Check for invalid leg combinations (e.g., same market over + under)."""
    conflicts = []
    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            # Same player, opposite direction on same market
            if (legs[i].player_name and
                    legs[i].player_name == legs[j].player_name and
                    legs[i].market == legs[j].market and
                    legs[i].direction != legs[j].direction):
                conflicts.append(
                    f"Conflict: {legs[i].player_name} {legs[i].market} "
                    f"{legs[i].direction} vs {legs[j].direction}"
                )
            # Explicit conflict pairs
            for ca, da, cb, db in CONFLICT_PAIRS:
                if (legs[i].market == ca and legs[i].direction == da and
                        legs[j].market == cb and legs[j].direction == db):
                    conflicts.append(
                        f"Conflict: {legs[i].market} {legs[i].direction} "
                        f"vs {legs[j].market} {legs[j].direction}"
                    )
    return conflicts


def build_sgp(legs: list[SGPLeg], sport: str = "nba") -> SGPAnalysis:
    """Build and analyze a same-game parlay with correlation adjustments.

    Uses a simplified Gaussian copula approach to adjust the naive
    independent-probability estimate based on known correlations.
    Tags correlated legs as "LINKED" (inspired by EdgeSlip).

    Args:
        sport: Short sport key or API sport key for correlation lookup.
    """
    from sba.utils.odds_math import decimal_to_american

    if len(legs) < 2:
        raise ValueError("SGP requires at least 2 legs")

    # Check for conflicts first
    conflicts = check_conflicts(legs)

    # Naive probability (assumes independence)
    naive_prob = 1.0
    for leg in legs:
        naive_prob *= leg.implied_prob

    # Calculate pairwise correlations and adjust
    correlations = []
    total_adjustment = 0.0

    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            corr = get_correlation(
                legs[i].market, legs[i].direction,
                legs[j].market, legs[j].direction,
                sport=sport,
            )
            if corr != 0:
                adjustment = corr * legs[i].implied_prob * legs[j].implied_prob * 0.5
                total_adjustment += adjustment

                # Tag as LINKED if correlation is significant
                link_tag = "LINKED" if abs(corr) >= 0.15 else "weak"

                correlations.append({
                    "leg_a": f"{legs[i].player_name} {legs[i].market} {legs[i].direction}",
                    "leg_b": f"{legs[j].player_name} {legs[j].market} {legs[j].direction}",
                    "correlation": round(corr, 3),
                    "adjustment": round(adjustment, 6),
                    "tag": link_tag,
                })

    correlated_prob = max(0.001, min(0.999, naive_prob + total_adjustment))

    naive_dec = 1.0 / naive_prob if naive_prob > 0 else 100.0
    corr_dec = 1.0 / correlated_prob if correlated_prob > 0 else 100.0

    naive_american = decimal_to_american(naive_dec)
    corr_american = decimal_to_american(corr_dec)

    pct_change = ((correlated_prob - naive_prob) / naive_prob * 100) if naive_prob > 0 else 0

    logger.info(
        "SGP: %d legs, naive=%.4f, correlated=%.4f, adjustment=%+.1f%%",
        len(legs), naive_prob, correlated_prob, pct_change,
    )

    return SGPAnalysis(
        legs=legs,
        naive_probability=round(naive_prob, 6),
        correlated_probability=round(correlated_prob, 6),
        naive_odds_decimal=round(naive_dec, 4),
        correlated_odds_decimal=round(corr_dec, 4),
        naive_odds_american=naive_american,
        correlated_odds_american=corr_american,
        correlation_adjustment=round(pct_change, 2),
        correlations=correlations,
        conflicts=conflicts,
    )
