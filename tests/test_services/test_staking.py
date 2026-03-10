"""Tests for the staking strategies service."""

import pytest

from sba.services.staking import (
    compare_strategies,
    fibonacci_recovery,
    flat_stake,
    kelly_criterion,
    percentage_bankroll,
    proportional_ev,
)


class TestFlatStake:
    def test_default_2_percent(self):
        r = flat_stake(1000)
        assert r.stake == 20.0
        assert r.strategy == "flat"

    def test_custom_percent(self):
        r = flat_stake(1000, 5.0)
        assert r.stake == 50.0

    def test_zero_bankroll(self):
        r = flat_stake(0)
        assert r.stake == 0.0


class TestKellyCriterion:
    def test_positive_edge(self):
        r = kelly_criterion(1000, 2.0, 0.55, 0.25)
        assert r.stake > 0
        assert r.strategy == "kelly"

    def test_no_edge(self):
        r = kelly_criterion(1000, 2.0, 0.50, 0.25)
        assert r.stake == 0  # no edge at fair odds

    def test_negative_edge(self):
        r = kelly_criterion(1000, 2.0, 0.40, 0.25)
        assert r.stake == 0

    def test_quarter_kelly_smaller_than_half(self):
        q = kelly_criterion(1000, 2.0, 0.60, 0.25)
        h = kelly_criterion(1000, 2.0, 0.60, 0.5)
        assert q.stake < h.stake

    def test_full_kelly(self):
        r = kelly_criterion(1000, 2.0, 0.60, 1.0)
        assert r.stake == pytest.approx(200.0, abs=0.1)  # full kelly = 20%


class TestPercentageBankroll:
    def test_medium_confidence(self):
        r = percentage_bankroll(1000, "medium")
        assert r.stake == 20.0

    def test_high_confidence(self):
        r = percentage_bankroll(1000, "high")
        assert r.stake == 30.0

    def test_max_confidence(self):
        r = percentage_bankroll(1000, "max")
        assert r.stake == 50.0


class TestFibonacciRecovery:
    def test_no_losses(self):
        r = fibonacci_recovery(1000, 0)
        assert r.stake == 10.0  # 1% base × fib(0)=1

    def test_after_3_losses(self):
        r = fibonacci_recovery(1000, 3)
        assert r.stake > 10.0  # should be higher

    def test_capped_at_5_percent(self):
        r = fibonacci_recovery(1000, 20)
        assert r.stake <= 50.0  # 5% cap


class TestProportionalEv:
    def test_positive_ev(self):
        r = proportional_ev(1000, 5.0)
        assert r.stake == 25.0  # 5% EV × 0.5 = 2.5%

    def test_zero_ev(self):
        r = proportional_ev(1000, 0)
        assert r.stake == 0

    def test_capped(self):
        r = proportional_ev(1000, 20.0, max_pct=5.0)
        assert r.stake == 50.0  # capped at 5%


class TestCompareStrategies:
    def test_returns_multiple_strategies(self):
        results = compare_strategies(1000)
        assert len(results) >= 5
        strategies = {r["strategy"] for r in results}
        assert "flat" in strategies
        assert "kelly" in strategies
        assert "percentage" in strategies
        assert "proportional_ev" in strategies

    def test_all_have_required_fields(self):
        results = compare_strategies(1000)
        for r in results:
            assert "strategy" in r
            assert "stake" in r
            assert "unit_pct" in r
            assert "reasoning" in r

    def test_includes_fibonacci_when_losing(self):
        results = compare_strategies(1000, loss_streak=3)
        strategies = {r["strategy"] for r in results}
        assert "fibonacci" in strategies
