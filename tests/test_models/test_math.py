"""Tests for odds math, EV, Kelly, and Poisson calculations."""

import pytest
from sba.utils.odds_math import (
    american_to_decimal, decimal_to_american,
    american_to_implied_prob, remove_vig, calculate_vig,
)
from sba.models.statistical.kelly import full_kelly, fractional_kelly, kelly_stake
from sba.models.statistical.ev import calculate_ev
from sba.models.statistical.poisson import poisson_prob, over_under_prob


class TestOddsMath:
    def test_american_to_decimal_positive(self):
        assert american_to_decimal(150) == 2.5

    def test_american_to_decimal_negative(self):
        assert american_to_decimal(-200) == 1.5

    def test_decimal_to_american_positive(self):
        assert decimal_to_american(2.5) == 150

    def test_decimal_to_american_negative(self):
        assert decimal_to_american(1.5) == -200

    def test_american_to_implied_prob_favorite(self):
        prob = american_to_implied_prob(-150)
        assert abs(prob - 0.6) < 0.001

    def test_american_to_implied_prob_underdog(self):
        prob = american_to_implied_prob(200)
        assert abs(prob - 0.3333) < 0.001

    def test_remove_vig(self):
        # Two-way market with vig
        outcomes = [
            {"price_decimal": 1.91},  # ~52.36% implied
            {"price_decimal": 1.91},  # ~52.36% implied
        ]
        fair = remove_vig(outcomes)
        assert abs(fair[0] - 0.5) < 0.001
        assert abs(fair[1] - 0.5) < 0.001

    def test_calculate_vig(self):
        outcomes = [
            {"price_decimal": 1.91},
            {"price_decimal": 1.91},
        ]
        vig = calculate_vig(outcomes)
        assert vig > 0  # Should have positive vig


class TestEV:
    def test_positive_ev(self):
        # 55% chance at +100 (2.0 decimal)
        ev = calculate_ev(0.55, 2.0)
        assert ev == pytest.approx(0.10, abs=0.001)

    def test_negative_ev(self):
        # 45% chance at even money
        ev = calculate_ev(0.45, 2.0)
        assert ev < 0

    def test_break_even(self):
        # 50% at even money
        ev = calculate_ev(0.50, 2.0)
        assert abs(ev) < 0.001


class TestKelly:
    def test_full_kelly_positive_edge(self):
        # 55% at +100 -> Kelly says bet 10%
        k = full_kelly(0.55, 2.0)
        assert k == pytest.approx(0.10, abs=0.001)

    def test_full_kelly_no_edge(self):
        k = full_kelly(0.50, 2.0)
        assert k == pytest.approx(0.0, abs=0.001)

    def test_full_kelly_negative_edge(self):
        k = full_kelly(0.40, 2.0)
        assert k == 0.0

    def test_fractional_kelly(self):
        fk = fractional_kelly(0.55, 2.0, 0.25)
        assert fk == pytest.approx(0.025, abs=0.001)

    def test_kelly_stake(self):
        stake = kelly_stake(0.55, 2.0, 1000.0, 0.25)
        assert stake == pytest.approx(25.0, abs=0.5)


class TestPoisson:
    def test_poisson_prob_zero(self):
        p = poisson_prob(0, 2.5)
        assert 0 < p < 1

    def test_poisson_prob_sums_to_one(self):
        total = sum(poisson_prob(k, 2.5) for k in range(50))
        assert abs(total - 1.0) < 0.001

    def test_over_under_low_scoring(self):
        # Soccer-like: home expects 1.5, away expects 1.0
        over_p, under_p = over_under_prob(2.5, 1.5, 1.0)
        assert over_p + under_p <= 1.0
        assert over_p > 0 and under_p > 0

    def test_over_under_high_scoring(self):
        # NBA-like: home expects 112, away expects 108
        over_p, under_p = over_under_prob(220.5, 112, 108)
        assert over_p + under_p <= 1.001  # Normal approx may have tiny rounding
        assert over_p > 0 and under_p > 0
