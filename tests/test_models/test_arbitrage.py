"""Tests for arbitrage detection and stake calculation."""

import pytest
from datetime import datetime

from sba.models.domain import (
    ArbOpportunity,
    ArbOutcome,
    BookmakerOdds,
    Event,
    EventOdds,
    Outcome,
)
from sba.models.statistical.arbitrage import (
    calculate_stakes,
    detect_arbitrage,
    scan_arbitrage,
)


def _make_event() -> Event:
    return Event(
        id="arb-test-1",
        sport="basketball_nba",
        home_team="TeamA",
        away_team="TeamB",
        commence_time=datetime(2025, 6, 1, 19, 0),
    )


class TestCalculateStakes:
    def test_two_way_equal_odds(self):
        """Equal odds -> equal stakes."""
        stakes = calculate_stakes([2.0, 2.0], total_bankroll=100.0)
        assert len(stakes) == 2
        assert stakes[0] == pytest.approx(50.0)
        assert stakes[1] == pytest.approx(50.0)

    def test_two_way_unequal_odds(self):
        """Higher odds side gets smaller stake."""
        stakes = calculate_stakes([1.5, 3.0], total_bankroll=100.0)
        assert len(stakes) == 2
        # 1/1.5 = 0.667, 1/3.0 = 0.333, total = 1.0
        assert stakes[0] == pytest.approx(66.667, abs=0.01)
        assert stakes[1] == pytest.approx(33.333, abs=0.01)
        assert sum(stakes) == pytest.approx(100.0)

    def test_three_way_stakes(self):
        stakes = calculate_stakes([3.0, 4.0, 5.0], total_bankroll=1.0)
        assert len(stakes) == 3
        assert sum(stakes) == pytest.approx(1.0)
        # Largest odds -> smallest stake
        assert stakes[0] > stakes[1] > stakes[2]

    def test_default_bankroll(self):
        stakes = calculate_stakes([2.0, 2.0])
        assert sum(stakes) == pytest.approx(1.0)

    def test_empty_odds(self):
        stakes = calculate_stakes([])
        assert stakes == []

    def test_zero_odds_returns_zeros(self):
        stakes = calculate_stakes([0.0, 2.0])
        assert all(s == 0.0 for s in stakes)

    def test_payout_is_equal_across_outcomes(self):
        """The whole point: each outcome pays the same amount."""
        odds = [1.8, 2.3]
        bankroll = 1000.0
        stakes = calculate_stakes(odds, total_bankroll=bankroll)
        payouts = [s * o for s, o in zip(stakes, odds)]
        # All payouts should be equal
        assert payouts[0] == pytest.approx(payouts[1], abs=0.01)


class TestDetectArbitrage:
    def test_returns_none_when_no_arb(self):
        """When odds imply >= 100% combined, no arb exists."""
        event = _make_event()
        event_odds = EventOdds(
            event=event,
            bookmakers=[
                BookmakerOdds(
                    bookmaker="bookA",
                    market="h2h",
                    outcomes=[
                        Outcome(name="TeamA", price_american=-150, price_decimal=1.667),
                        Outcome(name="TeamB", price_american=130, price_decimal=2.3),
                    ],
                ),
                BookmakerOdds(
                    bookmaker="bookB",
                    market="h2h",
                    outcomes=[
                        Outcome(name="TeamA", price_american=-160, price_decimal=1.625),
                        Outcome(name="TeamB", price_american=120, price_decimal=2.2),
                    ],
                ),
            ],
        )
        result = detect_arbitrage(event_odds, "h2h")
        assert result is None

    def test_finds_arb_when_implied_prob_below_100(self):
        """When best odds across books sum to < 100% implied, arb exists."""
        event = _make_event()
        # bookA has great odds on TeamA, bookB has great odds on TeamB
        # 1/2.10 + 1/2.10 = 0.476 + 0.476 = 0.952 < 1.0 => arb
        event_odds = EventOdds(
            event=event,
            bookmakers=[
                BookmakerOdds(
                    bookmaker="bookA",
                    market="h2h",
                    outcomes=[
                        Outcome(name="TeamA", price_american=110, price_decimal=2.10),
                        Outcome(name="TeamB", price_american=-200, price_decimal=1.50),
                    ],
                ),
                BookmakerOdds(
                    bookmaker="bookB",
                    market="h2h",
                    outcomes=[
                        Outcome(name="TeamA", price_american=-200, price_decimal=1.50),
                        Outcome(name="TeamB", price_american=110, price_decimal=2.10),
                    ],
                ),
            ],
        )
        result = detect_arbitrage(event_odds, "h2h")
        assert result is not None
        assert isinstance(result, ArbOpportunity)
        assert result.total_implied_prob < 1.0
        assert result.profit_pct > 0
        assert len(result.outcomes) == 2
        # Best odds for each team should be 2.10
        for outcome in result.outcomes:
            assert outcome.odds_decimal == pytest.approx(2.10)

    def test_arb_profit_pct_calculation(self):
        """Verify profit_pct = (1/total_implied - 1) * 100."""
        event = _make_event()
        # 1/2.10 + 1/2.10 = 0.9524
        event_odds = EventOdds(
            event=event,
            bookmakers=[
                BookmakerOdds(
                    bookmaker="bookA",
                    market="h2h",
                    outcomes=[
                        Outcome(name="TeamA", price_american=110, price_decimal=2.10),
                        Outcome(name="TeamB", price_american=-110, price_decimal=1.91),
                    ],
                ),
                BookmakerOdds(
                    bookmaker="bookB",
                    market="h2h",
                    outcomes=[
                        Outcome(name="TeamA", price_american=-110, price_decimal=1.91),
                        Outcome(name="TeamB", price_american=110, price_decimal=2.10),
                    ],
                ),
            ],
        )
        result = detect_arbitrage(event_odds, "h2h")
        assert result is not None
        expected_total = 1.0 / 2.10 + 1.0 / 2.10
        expected_profit = (1.0 / expected_total - 1.0) * 100.0
        assert result.profit_pct == pytest.approx(expected_profit, abs=0.01)

    def test_returns_none_with_single_bookmaker(self):
        """A single bookmaker can't create an arb against itself (if market priced normally)."""
        event = _make_event()
        event_odds = EventOdds(
            event=event,
            bookmakers=[
                BookmakerOdds(
                    bookmaker="bookA",
                    market="h2h",
                    outcomes=[
                        Outcome(name="TeamA", price_american=-110, price_decimal=1.91),
                        Outcome(name="TeamB", price_american=-110, price_decimal=1.91),
                    ],
                ),
            ],
        )
        result = detect_arbitrage(event_odds, "h2h")
        # 1/1.91 + 1/1.91 = 1.047 >= 1.0 => no arb
        assert result is None

    def test_returns_none_with_single_outcome(self):
        """Less than 2 outcomes means no arb is possible."""
        event = _make_event()
        event_odds = EventOdds(
            event=event,
            bookmakers=[
                BookmakerOdds(
                    bookmaker="bookA",
                    market="h2h",
                    outcomes=[
                        Outcome(name="TeamA", price_american=100, price_decimal=2.0),
                    ],
                ),
            ],
        )
        result = detect_arbitrage(event_odds, "h2h")
        assert result is None

    def test_wrong_market_ignored(self):
        """Bookmakers with a different market key are ignored."""
        event = _make_event()
        event_odds = EventOdds(
            event=event,
            bookmakers=[
                BookmakerOdds(
                    bookmaker="bookA",
                    market="spreads",
                    outcomes=[
                        Outcome(name="TeamA", price_american=110, price_decimal=2.10),
                        Outcome(name="TeamB", price_american=110, price_decimal=2.10),
                    ],
                ),
            ],
        )
        result = detect_arbitrage(event_odds, "h2h")
        assert result is None

    def test_arb_outcomes_have_correct_bookmakers(self):
        """Each ArbOutcome should reference the bookmaker that has the best odds."""
        event = _make_event()
        event_odds = EventOdds(
            event=event,
            bookmakers=[
                BookmakerOdds(
                    bookmaker="bookA",
                    market="h2h",
                    outcomes=[
                        Outcome(name="TeamA", price_american=110, price_decimal=2.10),
                        Outcome(name="TeamB", price_american=-200, price_decimal=1.50),
                    ],
                ),
                BookmakerOdds(
                    bookmaker="bookB",
                    market="h2h",
                    outcomes=[
                        Outcome(name="TeamA", price_american=-200, price_decimal=1.50),
                        Outcome(name="TeamB", price_american=110, price_decimal=2.10),
                    ],
                ),
            ],
        )
        result = detect_arbitrage(event_odds, "h2h")
        assert result is not None
        outcome_map = {o.outcome_name: o.bookmaker for o in result.outcomes}
        assert outcome_map["TeamA"] == "bookA"
        assert outcome_map["TeamB"] == "bookB"


class TestScanArbitrage:
    def test_scan_returns_sorted_by_profit(self):
        """scan_arbitrage should return arbs sorted by profit_pct descending."""
        event1 = Event(
            id="e1", sport="nba", home_team="A", away_team="B",
            commence_time=datetime(2025, 6, 1, 19, 0),
        )
        event2 = Event(
            id="e2", sport="nba", home_team="C", away_team="D",
            commence_time=datetime(2025, 6, 1, 20, 0),
        )
        # Event1: smaller arb (2.05 each side => total_implied ~0.976)
        eo1 = EventOdds(event=event1, bookmakers=[
            BookmakerOdds(bookmaker="b1", market="h2h", outcomes=[
                Outcome(name="A", price_american=105, price_decimal=2.05),
                Outcome(name="B", price_american=-200, price_decimal=1.50),
            ]),
            BookmakerOdds(bookmaker="b2", market="h2h", outcomes=[
                Outcome(name="A", price_american=-200, price_decimal=1.50),
                Outcome(name="B", price_american=105, price_decimal=2.05),
            ]),
        ])
        # Event2: larger arb (2.20 each side => total_implied ~0.909)
        eo2 = EventOdds(event=event2, bookmakers=[
            BookmakerOdds(bookmaker="b1", market="h2h", outcomes=[
                Outcome(name="C", price_american=120, price_decimal=2.20),
                Outcome(name="D", price_american=-200, price_decimal=1.50),
            ]),
            BookmakerOdds(bookmaker="b2", market="h2h", outcomes=[
                Outcome(name="C", price_american=-200, price_decimal=1.50),
                Outcome(name="D", price_american=120, price_decimal=2.20),
            ]),
        ])

        arbs = scan_arbitrage([eo1, eo2], markets=["h2h"])
        assert len(arbs) == 2
        assert arbs[0].profit_pct > arbs[1].profit_pct

    def test_scan_no_arbs_returns_empty(self):
        event = _make_event()
        eo = EventOdds(event=event, bookmakers=[
            BookmakerOdds(bookmaker="b1", market="h2h", outcomes=[
                Outcome(name="TeamA", price_american=-110, price_decimal=1.91),
                Outcome(name="TeamB", price_american=-110, price_decimal=1.91),
            ]),
        ])
        arbs = scan_arbitrage([eo])
        assert arbs == []
