"""Tests for consensus and sharp probability calculations."""

import pytest
from sba.models.domain import BookmakerOdds, Outcome
from sba.models.statistical.implied_prob import consensus_probability, sharp_probability


def _make_bm(bookmaker: str, odds_pairs: list[tuple[str, float]]) -> BookmakerOdds:
    """Helper to create BookmakerOdds with decimal prices."""
    return BookmakerOdds(
        bookmaker=bookmaker,
        market="h2h",
        outcomes=[
            Outcome(name=name, price_american=0, price_decimal=price)
            for name, price in odds_pairs
        ],
    )


class TestConsensus:
    def test_single_bookmaker(self):
        bms = [_make_bm("fanduel", [("A", 1.91), ("B", 1.91)])]
        probs = consensus_probability(bms)
        assert abs(probs["A"] - 0.5) < 0.01
        assert abs(probs["B"] - 0.5) < 0.01

    def test_multiple_bookmakers_average(self):
        bms = [
            _make_bm("fanduel", [("A", 1.5), ("B", 2.5)]),
            _make_bm("draftkings", [("A", 1.6), ("B", 2.3)]),
        ]
        probs = consensus_probability(bms)
        assert "A" in probs
        assert "B" in probs
        assert abs(sum(probs.values()) - 1.0) < 0.05

    def test_empty_input(self):
        assert consensus_probability([]) == {}

    def test_probabilities_sum_near_one(self):
        bms = [
            _make_bm("pinnacle", [("A", 1.95), ("B", 1.95)]),
            _make_bm("fanduel", [("A", 1.91), ("B", 1.91)]),
            _make_bm("draftkings", [("A", 1.87), ("B", 1.93)]),
        ]
        probs = consensus_probability(bms)
        total = sum(probs.values())
        assert abs(total - 1.0) < 0.05


class TestSharpProbability:
    def test_uses_sharp_books_only(self):
        bms = [
            _make_bm("pinnacle", [("A", 1.95), ("B", 1.95)]),
            _make_bm("fanduel", [("A", 1.5), ("B", 2.5)]),
        ]
        probs = sharp_probability(bms, ["pinnacle"])
        # Should only use pinnacle's lines
        assert abs(probs["A"] - 0.5) < 0.02

    def test_falls_back_to_consensus(self):
        bms = [
            _make_bm("fanduel", [("A", 1.91), ("B", 1.91)]),
        ]
        probs = sharp_probability(bms, ["pinnacle"])
        # No pinnacle available, should fall back to consensus
        assert len(probs) == 2

    def test_multiple_sharp_books(self):
        bms = [
            _make_bm("pinnacle", [("A", 1.92), ("B", 1.96)]),
            _make_bm("circa", [("A", 1.90), ("B", 1.98)]),
            _make_bm("fanduel", [("A", 1.80), ("B", 2.10)]),
        ]
        probs = sharp_probability(bms, ["pinnacle", "circa"])
        assert "A" in probs
        assert "B" in probs
