"""Tests for public money / sharp vs public tracker."""

import pytest

from sba.services.public_money import (
    analyze_public_money,
    simulate_public_money,
)


class TestAnalyzePublicMoney:
    def test_detects_sharp_divergence(self):
        outcomes = [
            {"name": "Lakers", "bet_pct": 70, "money_pct": 45},
            {"name": "Celtics", "bet_pct": 30, "money_pct": 55},
        ]
        result = analyze_public_money("evt1", "h2h", outcomes)
        assert result.sharp_signal == "Celtics"
        assert result.signal_strength in ("moderate", "strong")

    def test_no_divergence(self):
        outcomes = [
            {"name": "A", "bet_pct": 50, "money_pct": 50},
            {"name": "B", "bet_pct": 50, "money_pct": 50},
        ]
        result = analyze_public_money("evt1", "h2h", outcomes)
        assert result.signal_strength == "none"

    def test_strong_signal(self):
        outcomes = [
            {"name": "A", "bet_pct": 75, "money_pct": 40},
            {"name": "B", "bet_pct": 25, "money_pct": 60},
        ]
        result = analyze_public_money("evt1", "h2h", outcomes)
        assert result.signal_strength == "strong"

    def test_weak_signal(self):
        outcomes = [
            {"name": "A", "bet_pct": 55, "money_pct": 48},
            {"name": "B", "bet_pct": 45, "money_pct": 52},
        ]
        result = analyze_public_money("evt1", "h2h", outcomes)
        assert result.signal_strength in ("weak", "none")

    def test_empty_outcomes(self):
        result = analyze_public_money("evt1", "h2h", [])
        assert result.signal_strength == "none"
        assert result.sharp_signal is None

    def test_outcomes_populated(self):
        outcomes = [
            {"name": "A", "bet_pct": 60, "money_pct": 40},
            {"name": "B", "bet_pct": 40, "money_pct": 60},
        ]
        result = analyze_public_money("evt1", "h2h", outcomes)
        assert len(result.outcomes) == 2
        assert result.outcomes[0].bet_pct == 60
        assert result.outcomes[1].money_pct == 60

    def test_divergence_calculated(self):
        outcomes = [
            {"name": "A", "bet_pct": 60, "money_pct": 40},
        ]
        result = analyze_public_money("evt1", "h2h", outcomes)
        assert result.outcomes[0].divergence == -20.0

    def test_description_populated(self):
        outcomes = [
            {"name": "Lakers", "bet_pct": 70, "money_pct": 45},
            {"name": "Celtics", "bet_pct": 30, "money_pct": 55},
        ]
        result = analyze_public_money("evt1", "h2h", outcomes)
        assert len(result.description) > 0


class TestSimulatePublicMoney:
    def test_favorite_gets_more_public_bets(self):
        result = simulate_public_money("evt1", "Lakers", "Celtics", -200, 170)
        lakers_data = next(o for o in result.outcomes if o.outcome == "Lakers")
        assert lakers_data.bet_pct > 50

    def test_underdog_gets_fewer_bets(self):
        result = simulate_public_money("evt1", "Lakers", "Celtics", -200, 170)
        celtics_data = next(o for o in result.outcomes if o.outcome == "Celtics")
        assert celtics_data.bet_pct < 50

    def test_even_matchup(self):
        result = simulate_public_money("evt1", "A", "B", -110, -110)
        a = next(o for o in result.outcomes if o.outcome == "A")
        assert 45 <= a.bet_pct <= 55

    def test_returns_analysis(self):
        result = simulate_public_money("evt1", "A", "B", -150, 130)
        assert result.event_id == "evt1"
        assert result.market == "h2h"
        assert len(result.outcomes) == 2
