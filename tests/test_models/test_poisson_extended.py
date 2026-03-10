"""Extended Poisson model tests."""

import pytest
from sba.models.statistical.poisson import (
    poisson_prob,
    over_under_prob,
    moneyline_from_poisson,
    _normal_cdf,
)


class TestPoissonEdgeCases:
    def test_zero_lambda(self):
        p = poisson_prob(0, 0.0)
        assert p == 1.0

    def test_zero_lambda_nonzero_k(self):
        p = poisson_prob(5, 0.0)
        assert p == 0.0

    def test_negative_lambda(self):
        p = poisson_prob(0, -1.0)
        assert p == 1.0

    def test_large_k(self):
        p = poisson_prob(100, 50.0)
        assert p >= 0  # Should not overflow


class TestOverUnder:
    def test_push_excluded(self):
        """Over + Under should be < 1.0 when push is possible."""
        over_p, under_p = over_under_prob(3.0, 1.5, 1.5)
        assert over_p + under_p < 1.0

    def test_half_line_no_push(self):
        """Half-point lines eliminate pushes, so over + under should be ~1.0."""
        over_p, under_p = over_under_prob(2.5, 1.5, 1.0)
        assert abs(over_p + under_p - 1.0) < 0.01

    def test_very_high_line(self):
        over_p, under_p = over_under_prob(300.0, 112, 108)
        assert under_p > over_p


class TestMoneyline:
    def test_equal_teams(self):
        home, draw, away = moneyline_from_poisson(1.5, 1.5)
        assert abs(home - away) < 0.01
        assert draw > 0

    def test_sums_to_one(self):
        home, draw, away = moneyline_from_poisson(2.0, 1.0)
        assert abs(home + draw + away - 1.0) < 0.01

    def test_stronger_home(self):
        home, draw, away = moneyline_from_poisson(3.0, 1.0)
        assert home > away


class TestNormalCDF:
    def test_zero(self):
        assert abs(_normal_cdf(0) - 0.5) < 0.001

    def test_large_positive(self):
        assert _normal_cdf(5.0) > 0.999

    def test_large_negative(self):
        assert _normal_cdf(-5.0) < 0.001
