"""Tests for SGP correlation engine."""

import pytest

from sba.services.correlations import (
    SGPLeg,
    build_sgp,
    get_correlation,
)


def _leg(market, direction, odds_american, implied_prob, player="Test"):
    """Helper to create an SGPLeg."""
    return SGPLeg(
        market=market,
        selection=f"{player} {market}",
        direction=direction,
        odds_american=odds_american,
        odds_decimal=1 / implied_prob,
        implied_prob=implied_prob,
        player_name=player,
    )


class TestGetCorrelation:
    def test_known_correlation(self):
        corr = get_correlation("player_points", "over", "player_threes", "over")
        assert corr == 0.45

    def test_reverse_lookup(self):
        """Reverse order should return same correlation."""
        corr = get_correlation("player_threes", "over", "player_points", "over")
        assert corr == 0.45

    def test_unknown_player_props_default(self):
        """Unknown player prop pairs should return 0.05."""
        corr = get_correlation("player_steals", "over", "player_blocks", "over")
        assert corr == 0.05

    def test_unknown_non_player_zero(self):
        """Non-player unknown pairs return 0."""
        corr = get_correlation("total_rebounds", "over", "first_half", "over")
        assert corr == 0.0

    def test_spread_team_win_high_correlation(self):
        corr = get_correlation("spread", "cover", "team_win", "yes")
        assert corr == 0.85

    def test_inverse_correlation(self):
        corr = get_correlation("player_points", "over", "player_points", "under")
        assert corr == -1.0


class TestBuildSGP:
    def test_requires_minimum_legs(self):
        leg = _leg("player_points", "over", -110, 0.5)
        with pytest.raises(ValueError, match="at least 2"):
            build_sgp([leg])

    def test_two_uncorrelated_legs(self):
        legs = [
            _leg("total_rebounds", "over", -110, 0.5, "Player A"),
            _leg("first_half", "over", -110, 0.5, "Player B"),
        ]
        result = build_sgp(legs)
        assert result.naive_probability == pytest.approx(0.25, abs=0.01)
        # No correlation, so adjusted should equal naive
        assert result.correlated_probability == pytest.approx(0.25, abs=0.01)

    def test_positive_correlation_increases_prob(self):
        legs = [
            _leg("player_points", "over", -110, 0.5),
            _leg("player_threes", "over", -110, 0.5),
        ]
        result = build_sgp(legs)
        # 0.45 correlation should push probability up
        assert result.correlated_probability > result.naive_probability

    def test_negative_correlation_decreases_prob(self):
        legs = [
            _leg("player_points", "over", -110, 0.5),
            _leg("player_points", "under", 100, 0.5),
        ]
        result = build_sgp(legs)
        assert result.correlated_probability < result.naive_probability

    def test_returns_american_odds(self):
        legs = [
            _leg("player_points", "over", -110, 0.5),
            _leg("player_assists", "over", -110, 0.5),
        ]
        result = build_sgp(legs)
        assert isinstance(result.naive_odds_american, int)
        assert isinstance(result.correlated_odds_american, int)

    def test_correlation_details_populated(self):
        legs = [
            _leg("player_points", "over", -110, 0.5),
            _leg("player_threes", "over", -110, 0.5),
        ]
        result = build_sgp(legs)
        assert len(result.correlations) > 0
        assert "correlation" in result.correlations[0]
        assert "leg_a" in result.correlations[0]

    def test_three_legs(self):
        legs = [
            _leg("player_points", "over", -110, 0.5, "LeBron"),
            _leg("player_assists", "over", -110, 0.5, "LeBron"),
            _leg("player_rebounds", "over", -110, 0.5, "LeBron"),
        ]
        result = build_sgp(legs)
        assert result.naive_probability == pytest.approx(0.125, abs=0.01)
        assert len(result.legs) == 3

    def test_probability_clamped(self):
        """Probabilities should stay within (0, 1)."""
        legs = [
            _leg("player_points", "over", -110, 0.9),
            _leg("player_threes", "over", -110, 0.9),
        ]
        result = build_sgp(legs)
        assert 0 < result.correlated_probability < 1

    def test_correlation_adjustment_percentage(self):
        legs = [
            _leg("player_points", "over", -110, 0.5),
            _leg("player_threes", "over", -110, 0.5),
        ]
        result = build_sgp(legs)
        # adjustment should be nonzero for correlated legs
        assert result.correlation_adjustment != 0
