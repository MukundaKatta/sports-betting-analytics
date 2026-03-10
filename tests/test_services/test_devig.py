"""Tests for multi-method devig engine."""

import pytest

from sba.services.devig import (
    devig_additive,
    devig_multiplicative,
    devig_power,
    devig_worst_case,
    devig_single,
    devig_multi,
)


class TestDevigMethods:
    def test_multiplicative_sums_to_one(self):
        result = devig_multiplicative([0.524, 0.524])
        assert sum(result) == pytest.approx(1.0, abs=0.001)

    def test_additive_sums_to_one(self):
        result = devig_additive([0.524, 0.524])
        assert sum(result) == pytest.approx(1.0, abs=0.001)

    def test_power_sums_to_one(self):
        result = devig_power([0.524, 0.524])
        assert sum(result) == pytest.approx(1.0, abs=0.001)

    def test_worst_case_sums_to_one(self):
        result = devig_worst_case([0.524, 0.524])
        assert sum(result) == pytest.approx(1.0, abs=0.001)

    def test_even_odds_produce_fifty_fifty(self):
        """-110/-110 should devig to ~50/50."""
        result = devig_multiplicative([0.524, 0.524])
        assert result[0] == pytest.approx(0.5, abs=0.01)

    def test_favorite_has_higher_prob(self):
        result = devig_multiplicative([0.667, 0.4])  # ~-200/+150
        assert result[0] > result[1]

    def test_worst_case_more_conservative(self):
        """Worst case should give less generous fair odds to the favorite."""
        probs = [0.7, 0.38]  # Heavy favorite
        mult = devig_multiplicative(probs)
        worst = devig_worst_case(probs)
        # Worst case gives lower probability to favorite
        assert worst[0] <= mult[0] + 0.02  # Roughly equal or lower

    def test_empty_input(self):
        assert devig_multiplicative([]) == []
        assert devig_additive([]) == []

    def test_three_way_market(self):
        result = devig_multiplicative([0.4, 0.35, 0.35])
        assert sum(result) == pytest.approx(1.0, abs=0.001)
        assert len(result) == 3


class TestDevigSingle:
    def test_basic_devig(self):
        result = devig_single([-110, -110])
        assert result.method == "multiplicative"
        assert len(result.fair_probabilities) == 2
        assert sum(result.fair_probabilities) == pytest.approx(1.0, abs=0.001)
        assert result.vig_removed > 0

    def test_with_outcome_names(self):
        result = devig_single([-150, 130], outcome_names=["Lakers", "Celtics"])
        assert result.outcome_names == ["Lakers", "Celtics"]
        assert result.fair_probabilities[0] > result.fair_probabilities[1]

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="Unknown method"):
            devig_single([-110, -110], method="nonexistent")

    def test_vig_calculation(self):
        result = devig_single([-110, -110])
        assert result.vig_removed == pytest.approx(4.55, abs=0.5)

    def test_returns_american_odds(self):
        result = devig_single([-110, -110])
        assert all(isinstance(o, int) for o in result.fair_odds_american)

    def test_all_methods_work(self):
        for method in ["multiplicative", "additive", "power", "worst_case"]:
            result = devig_single([-110, -110], method=method)
            assert sum(result.fair_probabilities) == pytest.approx(1.0, abs=0.001)


class TestDevigMulti:
    def test_basic_multi_book(self):
        book_odds = [
            {"bookmaker": "pinnacle", "odds": [-108, -104]},
            {"bookmaker": "fanduel", "odds": [-110, -110]},
        ]
        result = devig_multi(book_odds)
        assert len(result.methods) == 4  # all methods
        assert sum(result.weighted_fair_probs) == pytest.approx(1.0, abs=0.01)

    def test_books_used_tracked(self):
        book_odds = [
            {"bookmaker": "pinnacle", "odds": [-110, -110]},
            {"bookmaker": "draftkings", "odds": [-115, -105]},
        ]
        result = devig_multi(book_odds)
        assert "pinnacle" in result.books_used
        assert "draftkings" in result.books_used

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            devig_multi([])

    def test_single_book_works(self):
        result = devig_multi([{"bookmaker": "pinnacle", "odds": [-110, -110]}])
        assert len(result.weighted_fair_probs) == 2

    def test_custom_methods(self):
        book_odds = [{"bookmaker": "pinnacle", "odds": [-110, -110]}]
        result = devig_multi(book_odds, methods=["multiplicative", "power"])
        assert len(result.methods) == 2

    def test_outcome_names(self):
        book_odds = [{"bookmaker": "pinnacle", "odds": [-110, -110]}]
        result = devig_multi(book_odds, outcome_names=["Home", "Away"])
        assert result.outcomes == ["Home", "Away"]
