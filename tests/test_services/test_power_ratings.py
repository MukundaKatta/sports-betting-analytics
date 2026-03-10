"""Tests for power ratings service."""

import pytest

from sba.services.power_ratings import (
    TeamRating,
    analyze_matchup,
    calculate_ratings_from_odds,
    DEFAULT_RATING,
    HOME_ADVANTAGE,
)


def _event(home, away, home_odds, away_odds, sport="basketball_nba"):
    return {
        "home_team": home,
        "away_team": away,
        "home_odds_american": home_odds,
        "away_odds_american": away_odds,
        "sport": sport,
    }


class TestCalculateRatingsFromOdds:
    def test_heavy_favorite_gets_higher_rating(self):
        events = [_event("Lakers", "Hornets", -300, 250)]
        ratings = calculate_ratings_from_odds(events)
        lakers = next(r for r in ratings if r.team == "Lakers")
        hornets = next(r for r in ratings if r.team == "Hornets")
        assert lakers.rating > hornets.rating

    def test_even_matchup_similar_ratings(self):
        events = [_event("TeamA", "TeamB", -110, -110)]
        ratings = calculate_ratings_from_odds(events)
        a = next(r for r in ratings if r.team == "TeamA")
        b = next(r for r in ratings if r.team == "TeamB")
        # Should be roughly similar (home advantage accounted for)
        assert abs(a.rating - b.rating) < 200

    def test_ranks_assigned(self):
        events = [
            _event("Lakers", "Hornets", -300, 250),
            _event("Celtics", "Pistons", -250, 200),
        ]
        ratings = calculate_ratings_from_odds(events)
        assert ratings[0].rank == 1
        assert ratings[1].rank == 2

    def test_empty_events(self):
        assert calculate_ratings_from_odds([]) == []

    def test_missing_odds_skipped(self):
        events = [{"home_team": "A", "away_team": "B"}]
        assert calculate_ratings_from_odds(events) == []

    def test_multiple_events_same_team(self):
        events = [
            _event("Lakers", "Hornets", -200, 170),
            _event("Lakers", "Pistons", -250, 200),
        ]
        ratings = calculate_ratings_from_odds(events)
        lakers = next(r for r in ratings if r.team == "Lakers")
        assert lakers.games_rated == 2

    def test_win_pct_populated(self):
        events = [_event("Lakers", "Hornets", -200, 170)]
        ratings = calculate_ratings_from_odds(events)
        for r in ratings:
            assert 0 < r.implied_win_pct < 1

    def test_sport_preserved(self):
        events = [_event("Patriots", "Jets", -150, 130, "americanfootball_nfl")]
        ratings = calculate_ratings_from_odds(events)
        assert ratings[0].sport == "americanfootball_nfl"


class TestAnalyzeMatchup:
    @pytest.fixture
    def sample_ratings(self):
        return [
            TeamRating(team="Lakers", sport="nba", rating=1600),
            TeamRating(team="Celtics", sport="nba", rating=1550),
            TeamRating(team="Hornets", sport="nba", rating=1400),
        ]

    def test_home_advantage_matters(self, sample_ratings):
        result = analyze_matchup("Lakers", "Celtics", sample_ratings)
        assert result.home_win_prob > 0.5  # Lakers home + higher rating

    def test_stronger_away_can_be_favored(self, sample_ratings):
        result = analyze_matchup("Hornets", "Lakers", sample_ratings)
        # Lakers are much stronger, should still be favored even away
        assert result.away_win_prob > result.home_win_prob

    def test_predicted_spread(self, sample_ratings):
        result = analyze_matchup("Lakers", "Hornets", sample_ratings)
        # Lakers much stronger + home, spread should be negative (home favored)
        assert result.predicted_spread < 0

    def test_probabilities_sum_to_one(self, sample_ratings):
        result = analyze_matchup("Lakers", "Celtics", sample_ratings)
        assert result.home_win_prob + result.away_win_prob == pytest.approx(1.0)

    def test_unknown_team_gets_default(self, sample_ratings):
        result = analyze_matchup("Lakers", "UnknownTeam", sample_ratings)
        assert result.away_rating == DEFAULT_RATING

    def test_rating_diff_calculated(self, sample_ratings):
        result = analyze_matchup("Lakers", "Celtics", sample_ratings)
        assert result.rating_diff != 0

    def test_edge_with_market_spread(self, sample_ratings):
        result = analyze_matchup("Lakers", "Hornets", sample_ratings, market_spread=-5.0)
        # home_edge should be nonzero when market spread differs from model
        assert isinstance(result.home_edge, float)
        assert isinstance(result.away_edge, float)
