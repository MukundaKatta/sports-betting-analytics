"""Extended tests for odds math utilities."""

from sba.utils.odds_math import (
    american_to_decimal,
    american_to_implied_prob,
    calculate_vig,
    decimal_to_american,
    decimal_to_implied_prob,
    remove_vig,
)


class TestAmericanToDecimal:
    def test_even_money(self):
        assert american_to_decimal(100) == 2.0

    def test_heavy_favorite(self):
        result = american_to_decimal(-500)
        assert abs(result - 1.2) < 0.001

    def test_big_underdog(self):
        result = american_to_decimal(500)
        assert abs(result - 6.0) < 0.001


class TestDecimalToAmerican:
    def test_even_money(self):
        assert decimal_to_american(2.0) == 100

    def test_roundtrip_positive(self):
        for odds in [110, 150, 200, 300, 500]:
            decimal = american_to_decimal(odds)
            back = decimal_to_american(decimal)
            assert back == odds

    def test_roundtrip_negative(self):
        for odds in [-110, -150, -200, -300, -500]:
            decimal = american_to_decimal(odds)
            back = decimal_to_american(decimal)
            assert back == odds


class TestImpliedProb:
    def test_even_money(self):
        assert abs(american_to_implied_prob(100) - 0.5) < 0.001

    def test_decimal_zero(self):
        assert decimal_to_implied_prob(0) == 0.0

    def test_decimal_negative(self):
        assert decimal_to_implied_prob(-1.0) == 0.0

    def test_decimal_even(self):
        assert abs(decimal_to_implied_prob(2.0) - 0.5) < 0.001


class TestRemoveVig:
    def test_three_way_market(self):
        outcomes = [
            {"price_decimal": 2.0},
            {"price_decimal": 3.5},
            {"price_decimal": 4.0},
        ]
        fair = remove_vig(outcomes)
        assert abs(sum(fair) - 1.0) < 0.001

    def test_all_zero_prices(self):
        outcomes = [{"price_decimal": 0}, {"price_decimal": 0}]
        fair = remove_vig(outcomes)
        assert fair == [0.0, 0.0]


class TestCalculateVig:
    def test_no_vig_market(self):
        outcomes = [{"price_decimal": 2.0}, {"price_decimal": 2.0}]
        vig = calculate_vig(outcomes)
        assert abs(vig) < 0.001

    def test_standard_vig(self):
        # -110/-110 market has ~4.5% vig
        outcomes = [{"price_decimal": 1.909}, {"price_decimal": 1.909}]
        vig = calculate_vig(outcomes)
        assert 0.04 < vig < 0.06
