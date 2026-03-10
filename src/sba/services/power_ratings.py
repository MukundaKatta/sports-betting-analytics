"""Team power ratings and strength model.

Generates Elo-style power ratings from betting market data.
Used by OddsJam/Outlier/BetQL for team strength comparisons.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Initial Elo-style ratings for known teams
DEFAULT_RATING = 1500.0
K_FACTOR = 20.0  # How fast ratings update
HOME_ADVANTAGE = 65.0  # Elo points for home team


@dataclass
class TeamRating:
    """Power rating for a single team."""
    team: str
    sport: str
    rating: float = DEFAULT_RATING
    implied_win_pct: float = 0.5
    rank: int = 0
    games_rated: int = 0
    trend: float = 0.0  # Last 10 games rating change
    offensive_rating: float = 100.0
    defensive_rating: float = 100.0


@dataclass
class MatchupAnalysis:
    """Head-to-head matchup analysis between two teams."""
    home_team: str
    away_team: str
    home_rating: float
    away_rating: float
    home_win_prob: float
    away_win_prob: float
    predicted_spread: float
    predicted_total: float | None = None
    home_edge: float = 0.0  # vs market line
    away_edge: float = 0.0
    rating_diff: float = 0.0


def calculate_ratings_from_odds(events_with_odds: list[dict]) -> list[TeamRating]:
    """Calculate implied power ratings from closing odds.

    Uses the market's implied probabilities (with vig removed) as the
    source of truth for team strength, then converts to an Elo scale.
    """
    from sba.utils.odds_math import american_to_decimal, decimal_to_implied_prob

    team_data: dict[str, dict] = {}

    for event in events_with_odds:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        sport = event.get("sport", "")
        home_odds = event.get("home_odds_american")
        away_odds = event.get("away_odds_american")

        if not home or not away or home_odds is None or away_odds is None:
            continue

        # Calculate no-vig probabilities
        home_dec = american_to_decimal(home_odds)
        away_dec = american_to_decimal(away_odds)
        home_imp = decimal_to_implied_prob(home_dec)
        away_imp = decimal_to_implied_prob(away_dec)
        total_imp = home_imp + away_imp

        if total_imp == 0:
            continue

        home_fair = home_imp / total_imp
        away_fair = away_imp / total_imp

        # Convert fair probability to Elo rating
        # Elo formula: P(win) = 1 / (1 + 10^((Rb - Ra) / 400))
        # Solving for rating diff: diff = -400 * log10(1/P - 1)
        for team, fair_prob in [(home, home_fair), (away, away_fair)]:
            if team not in team_data:
                team_data[team] = {
                    "sport": sport,
                    "probs": [],
                    "ratings": [],
                }

            team_data[team]["probs"].append(fair_prob)

            # Convert to Elo-scale rating
            if 0 < fair_prob < 1:
                # Account for home/away
                if team == home:
                    adjustment = -HOME_ADVANTAGE  # Remove home advantage
                else:
                    adjustment = HOME_ADVANTAGE
                diff = -400 * math.log10(1 / fair_prob - 1) + adjustment
                team_data[team]["ratings"].append(DEFAULT_RATING + diff)

    # Build final ratings
    ratings = []
    for team, data in team_data.items():
        if not data["ratings"]:
            continue

        avg_rating = sum(data["ratings"]) / len(data["ratings"])
        avg_prob = sum(data["probs"]) / len(data["probs"])

        # Trend: compare last 3 vs overall
        if len(data["ratings"]) >= 5:
            recent = sum(data["ratings"][-3:]) / 3
            trend = recent - avg_rating
        else:
            trend = 0

        ratings.append(TeamRating(
            team=team,
            sport=data["sport"],
            rating=round(avg_rating, 1),
            implied_win_pct=round(avg_prob, 3),
            games_rated=len(data["ratings"]),
            trend=round(trend, 1),
        ))

    # Sort and assign ranks
    ratings.sort(key=lambda r: r.rating, reverse=True)
    for i, r in enumerate(ratings):
        r.rank = i + 1

    logger.info(f"Generated power ratings for {len(ratings)} teams")
    return ratings


def analyze_matchup(
    home_team: str,
    away_team: str,
    ratings: list[TeamRating],
    market_spread: float | None = None,
    market_total: float | None = None,
) -> MatchupAnalysis:
    """Analyze a matchup between two teams using power ratings."""
    home_rating = next((r for r in ratings if r.team == home_team), None)
    away_rating = next((r for r in ratings if r.team == away_team), None)

    hr = home_rating.rating if home_rating else DEFAULT_RATING
    ar = away_rating.rating if away_rating else DEFAULT_RATING

    # Add home advantage
    hr_adjusted = hr + HOME_ADVANTAGE

    # Elo win probability
    expected_home = 1.0 / (1.0 + 10.0 ** ((ar - hr_adjusted) / 400.0))
    expected_away = 1.0 - expected_home

    # Convert rating diff to predicted spread
    # Roughly: 1 point of spread ≈ 25 Elo points
    rating_diff = hr_adjusted - ar
    predicted_spread = round(-rating_diff / 25.0, 1)  # Negative = home favored

    # Edge vs market
    home_edge = 0.0
    away_edge = 0.0
    if market_spread is not None:
        model_spread = predicted_spread
        home_edge = round((market_spread - model_spread) * 0.5, 2)  # Positive = value on home
        away_edge = -home_edge

    return MatchupAnalysis(
        home_team=home_team,
        away_team=away_team,
        home_rating=round(hr, 1),
        away_rating=round(ar, 1),
        home_win_prob=round(expected_home, 4),
        away_win_prob=round(expected_away, 4),
        predicted_spread=predicted_spread,
        predicted_total=market_total,
        home_edge=home_edge,
        away_edge=away_edge,
        rating_diff=round(rating_diff, 1),
    )
