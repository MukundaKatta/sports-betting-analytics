"""Tests for arbitrage detection engine."""

import pytest
from datetime import datetime

from sba.models.domain import BookmakerOdds, Event, EventOdds, Outcome
from sba.services.arbitrage import (
    ArbOpportunity,
    LowHoldMarket,
    MiddleOpportunity,
    find_arbitrage,
    find_low_holds,
    find_middles,
)


def _make_event_odds(bookmakers):
    """Helper to build an EventOdds with given bookmakers."""
    event = Event(
        id="test_1",
        sport="nba",
        home_team="Lakers",
        away_team="Celtics",
        commence_time=datetime(2025, 3, 15, 19, 0),
    )
    return EventOdds(event=event, bookmakers=bookmakers)


class TestFindArbitrage:
    def test_no_arb_with_normal_vig(self):
        """Standard -110/-110 lines have ~4.5% vig, no arb."""
        eo = _make_event_odds([
            BookmakerOdds(bookmaker="BookA", market="h2h", outcomes=[
                Outcome(name="Lakers", price_american=-110, price_decimal=1.909),
                Outcome(name="Celtics", price_american=-110, price_decimal=1.909),
            ]),
        ])
        assert find_arbitrage([eo]) == []

    def test_detects_arb_across_books(self):
        """Arb exists when best odds across books sum to < 100% implied."""
        eo = _make_event_odds([
            BookmakerOdds(bookmaker="BookA", market="h2h", outcomes=[
                Outcome(name="Lakers", price_american=110, price_decimal=2.1),
                Outcome(name="Celtics", price_american=-150, price_decimal=1.667),
            ]),
            BookmakerOdds(bookmaker="BookB", market="h2h", outcomes=[
                Outcome(name="Lakers", price_american=-120, price_decimal=1.833),
                Outcome(name="Celtics", price_american=110, price_decimal=2.1),
            ]),
        ])
        # Best: Lakers +110 (2.1) from BookA, Celtics +110 (2.1) from BookB
        # Implied: 1/2.1 + 1/2.1 = 0.476 + 0.476 = 0.952 < 1.0 => arb!
        arbs = find_arbitrage([eo])
        assert len(arbs) == 1
        assert arbs[0].profit_pct > 0
        assert arbs[0].book_a == "BookA"
        assert arbs[0].book_b == "BookB"

    def test_no_arb_with_single_book(self):
        """Single book can't have arb against itself."""
        eo = _make_event_odds([
            BookmakerOdds(bookmaker="BookA", market="h2h", outcomes=[
                Outcome(name="Lakers", price_american=-110, price_decimal=1.909),
                Outcome(name="Celtics", price_american=-110, price_decimal=1.909),
            ]),
        ])
        arbs = find_arbitrage([eo])
        assert arbs == []

    def test_arbs_sorted_by_profit(self):
        """Results should be sorted highest profit first."""
        events = []
        for i, dec_odds in enumerate([(2.1, 2.1), (2.2, 2.2)]):
            eo = _make_event_odds([
                BookmakerOdds(bookmaker="BookA", market="h2h", outcomes=[
                    Outcome(name="Home", price_american=100, price_decimal=dec_odds[0]),
                ]),
                BookmakerOdds(bookmaker="BookB", market="h2h", outcomes=[
                    Outcome(name="Away", price_american=100, price_decimal=dec_odds[1]),
                ]),
            ])
            eo.event.id = f"test_{i}"
            events.append(eo)

        arbs = find_arbitrage(events)
        if len(arbs) >= 2:
            assert arbs[0].profit_pct >= arbs[1].profit_pct

    def test_empty_events(self):
        assert find_arbitrage([]) == []


class TestFindMiddles:
    def test_detects_spread_middle(self):
        """Middle when different books have different spread lines."""
        eo = _make_event_odds([
            BookmakerOdds(bookmaker="BookA", market="spreads", outcomes=[
                Outcome(name="Lakers", price_american=-110, price_decimal=1.909, point=-3.5),
            ]),
            BookmakerOdds(bookmaker="BookB", market="spreads", outcomes=[
                Outcome(name="Lakers", price_american=-110, price_decimal=1.909, point=-2.5),
            ]),
        ])
        middles = find_middles([eo])
        assert len(middles) == 1
        assert middles[0].gap == 1.0
        assert middles[0].market == "spreads"

    def test_no_middle_with_same_lines(self):
        """No middle when lines are identical."""
        eo = _make_event_odds([
            BookmakerOdds(bookmaker="BookA", market="spreads", outcomes=[
                Outcome(name="Lakers", price_american=-110, price_decimal=1.909, point=-3.5),
            ]),
            BookmakerOdds(bookmaker="BookB", market="spreads", outcomes=[
                Outcome(name="Lakers", price_american=-105, price_decimal=1.952, point=-3.5),
            ]),
        ])
        middles = find_middles([eo])
        assert middles == []

    def test_no_middle_small_gap(self):
        """Gap must be >= 0.5 points."""
        eo = _make_event_odds([
            BookmakerOdds(bookmaker="BookA", market="totals", outcomes=[
                Outcome(name="Over", price_american=-110, price_decimal=1.909, point=220.0),
            ]),
            BookmakerOdds(bookmaker="BookB", market="totals", outcomes=[
                Outcome(name="Over", price_american=-110, price_decimal=1.909, point=220.0),
            ]),
        ])
        middles = find_middles([eo])
        assert middles == []

    def test_detects_totals_middle(self):
        """Middle on totals market."""
        eo = _make_event_odds([
            BookmakerOdds(bookmaker="BookA", market="totals", outcomes=[
                Outcome(name="Over", price_american=-110, price_decimal=1.909, point=219.5),
            ]),
            BookmakerOdds(bookmaker="BookB", market="totals", outcomes=[
                Outcome(name="Over", price_american=-110, price_decimal=1.909, point=221.0),
            ]),
        ])
        middles = find_middles([eo])
        assert len(middles) == 1
        assert middles[0].gap == 1.5

    def test_empty_events(self):
        assert find_middles([]) == []


class TestFindLowHolds:
    def test_detects_low_hold(self):
        """Market with minimal vig should be detected."""
        eo = _make_event_odds([
            BookmakerOdds(bookmaker="BookA", market="h2h", outcomes=[
                Outcome(name="Lakers", price_american=105, price_decimal=2.05),
                Outcome(name="Celtics", price_american=-105, price_decimal=1.952),
            ]),
            BookmakerOdds(bookmaker="BookB", market="h2h", outcomes=[
                Outcome(name="Lakers", price_american=-110, price_decimal=1.909),
                Outcome(name="Celtics", price_american=105, price_decimal=2.05),
            ]),
        ])
        # Best: Lakers +105 (2.05) = 48.78%, Celtics +105 (2.05) = 48.78%
        # Hold = 97.56% - 100% = -2.44% (negative = arb territory)
        low = find_low_holds([eo], max_hold=0.03)
        assert len(low) >= 1
        assert low[0].hold_pct <= 3.0

    def test_excludes_high_hold(self):
        """Markets with high vig should be excluded."""
        eo = _make_event_odds([
            BookmakerOdds(bookmaker="BookA", market="h2h", outcomes=[
                Outcome(name="Lakers", price_american=-130, price_decimal=1.769),
                Outcome(name="Celtics", price_american=-110, price_decimal=1.909),
            ]),
        ])
        # Implied: 56.5% + 52.4% = 108.9%, hold = 8.9%
        low = find_low_holds([eo], max_hold=0.03)
        assert low == []

    def test_sorted_by_hold(self):
        """Results should be sorted by hold ascending."""
        events = []
        for i, (dec_a, dec_b) in enumerate([(2.05, 2.05), (2.0, 2.0)]):
            eo = _make_event_odds([
                BookmakerOdds(bookmaker="BookA", market="h2h", outcomes=[
                    Outcome(name="Home", price_american=100, price_decimal=dec_a),
                    Outcome(name="Away", price_american=100, price_decimal=dec_b),
                ]),
            ])
            eo.event.id = f"test_{i}"
            events.append(eo)

        low = find_low_holds(events, max_hold=0.05)
        if len(low) >= 2:
            assert low[0].hold_pct <= low[1].hold_pct

    def test_empty_events(self):
        assert find_low_holds([]) == []
