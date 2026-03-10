"""Tests for EV calculations and edge finding."""

from datetime import datetime

import pytest

from sba.models.domain import BookmakerOdds, Event, EventOdds, Outcome
from sba.models.statistical.ev import best_available_odds, calculate_ev, find_ev_opportunities


@pytest.fixture
def event():
    return Event(
        id="g1", sport="basketball_nba",
        home_team="Lakers", away_team="Celtics",
        commence_time=datetime(2025, 3, 15, 19, 0),
    )


class TestCalculateEV:
    def test_strong_positive_ev(self):
        ev = calculate_ev(0.60, 2.0)
        assert ev > 0.15

    def test_zero_ev(self):
        ev = calculate_ev(0.50, 2.0)
        assert abs(ev) < 0.001

    def test_negative_ev(self):
        ev = calculate_ev(0.40, 2.0)
        assert ev < 0

    def test_high_odds_positive_ev(self):
        # 15% chance at +900 (10.0 decimal)
        ev = calculate_ev(0.15, 10.0)
        assert ev > 0

    def test_heavy_favorite(self):
        # 80% at -400 (1.25 decimal)
        ev = calculate_ev(0.80, 1.25)
        assert abs(ev) < 0.05


class TestBestAvailableOdds:
    def test_finds_best_price(self, event):
        eo = EventOdds(event=event, bookmakers=[
            BookmakerOdds(bookmaker="fanduel", market="h2h", outcomes=[
                Outcome(name="Lakers", price_american=110, price_decimal=2.1),
            ]),
            BookmakerOdds(bookmaker="draftkings", market="h2h", outcomes=[
                Outcome(name="Lakers", price_american=120, price_decimal=2.2),
            ]),
        ])
        result = best_available_odds(eo, "h2h", "Lakers")
        assert result is not None
        book, odds = result
        assert book == "draftkings"
        assert odds.price_decimal == 2.2

    def test_returns_none_for_missing(self, event):
        eo = EventOdds(event=event, bookmakers=[])
        result = best_available_odds(eo, "h2h", "Lakers")
        assert result is None

    def test_filters_by_market(self, event):
        eo = EventOdds(event=event, bookmakers=[
            BookmakerOdds(bookmaker="fanduel", market="spreads", outcomes=[
                Outcome(name="Lakers", price_american=-110, price_decimal=1.909, point=-3.5),
            ]),
        ])
        result = best_available_odds(eo, "h2h", "Lakers")
        assert result is None


class TestFindEVOpportunities:
    def test_finds_positive_ev(self, sample_event_odds):
        # Model says Lakers are 65% to win, but best odds imply less
        model_probs = {
            "Los Angeles Lakers": 0.65,
            "Boston Celtics": 0.35,
        }
        opps = find_ev_opportunities(sample_event_odds, model_probs, "h2h", threshold=0.01)
        assert len(opps) > 0
        assert all(o.ev >= 0.01 for o in opps)

    def test_no_opportunities_below_threshold(self, sample_event_odds):
        # Model agrees with odds, no edge
        model_probs = {
            "Los Angeles Lakers": 0.58,
            "Boston Celtics": 0.42,
        }
        opps = find_ev_opportunities(sample_event_odds, model_probs, "h2h", threshold=0.10)
        assert len(opps) == 0

    def test_opportunities_sorted_by_ev(self, sample_event_odds):
        model_probs = {
            "Los Angeles Lakers": 0.70,
            "Boston Celtics": 0.50,
        }
        opps = find_ev_opportunities(sample_event_odds, model_probs, "h2h", threshold=0.0)
        if len(opps) >= 2:
            assert opps[0].ev >= opps[1].ev

    def test_confidence_levels(self, sample_event_odds):
        model_probs = {
            "Los Angeles Lakers": 0.80,
            "Boston Celtics": 0.20,
        }
        opps = find_ev_opportunities(sample_event_odds, model_probs, "h2h", threshold=0.0)
        for opp in opps:
            assert opp.confidence in ("low", "medium", "high")

    def test_kelly_sizing_included(self, sample_event_odds):
        model_probs = {
            "Los Angeles Lakers": 0.70,
            "Boston Celtics": 0.30,
        }
        opps = find_ev_opportunities(sample_event_odds, model_probs, "h2h", threshold=0.0)
        for opp in opps:
            assert opp.kelly_pct >= 0
            assert opp.recommended_stake >= 0
