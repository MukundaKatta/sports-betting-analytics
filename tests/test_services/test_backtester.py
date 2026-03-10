"""Tests for backtesting engine."""

import pytest

from sba.services.backtester import (
    Backtester,
    StrategyBacktestResult,
    run_backtest,
    WARMUP_GAMES,
    SIMULATED_ODDS_DECIMAL,
)


def _bets(wins=5, losses=5, odds=-110):
    """Generate simple test bet data."""
    dec = 1 + (100 / abs(odds)) if odds < 0 else 1 + (odds / 100)
    bets = []
    for i in range(wins):
        bets.append({"event": f"W{i}", "selection": "A", "odds_american": odds,
                      "odds_decimal": dec, "result": "win"})
    for i in range(losses):
        bets.append({"event": f"L{i}", "selection": "B", "odds_american": odds,
                      "odds_decimal": dec, "result": "loss"})
    return bets


class TestBacktesterInit:
    def test_can_instantiate(self):
        bt = Backtester()
        assert bt is not None

    def test_warmup_games_positive(self):
        assert WARMUP_GAMES > 0

    def test_simulated_odds_reasonable(self):
        assert 1.5 < SIMULATED_ODDS_DECIMAL < 2.5


class TestBacktesterPlayerProps:
    def test_returns_none_for_missing_player(self):
        bt = Backtester()
        result = bt.backtest_player_props(player_id=99999)
        assert result is None


class TestRunBacktest:
    def test_basic_backtest(self):
        result = run_backtest(_bets(5, 5))
        assert isinstance(result, StrategyBacktestResult)
        assert result.total_bets == 10
        assert result.wins == 5
        assert result.losses == 5

    def test_win_rate(self):
        result = run_backtest(_bets(8, 2))
        assert result.win_rate == 80.0

    def test_equity_curve_present(self):
        result = run_backtest(_bets(5, 5))
        assert len(result.equity_curve) > 0
        assert result.equity_curve[0]["bet"] == 0

    def test_stop_loss(self):
        result = run_backtest(_bets(0, 20), stop_loss=500)
        assert result.total_bets < 20

    def test_custom_strategy_name(self):
        result = run_backtest(_bets(3, 3), strategy_name="My Strategy")
        assert result.strategy_name == "My Strategy"

    def test_percentage_staking(self):
        result = run_backtest(_bets(5, 5), stake_type="percentage", stake_amount=2.0)
        assert result.total_bets == 10
        assert result.avg_stake > 0

    def test_empty_bets(self):
        result = run_backtest([])
        assert result.total_bets == 0
        assert result.total_profit == 0

    def test_all_wins_positive_profit(self):
        result = run_backtest(_bets(10, 0))
        assert result.total_profit > 0
        assert result.roi_pct > 0

    def test_grade_assignment(self):
        result = run_backtest(_bets(10, 0))
        assert result.grade in ("A+", "A", "B+", "B", "C", "D")

    def test_max_drawdown_non_negative(self):
        result = run_backtest(_bets(5, 5))
        assert result.max_drawdown >= 0
