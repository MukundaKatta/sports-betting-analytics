"""Tests for backtesting engine."""

import pytest

from sba.services.backtester import run_backtest


def _bets(wins=5, losses=5, odds=-110):
    """Generate simple test bet data."""
    bets = []
    for i in range(wins):
        bets.append({"event": f"W{i}", "selection": "A", "odds_american": odds, "result": "win"})
    for i in range(losses):
        bets.append({"event": f"L{i}", "selection": "B", "odds_american": odds, "result": "loss"})
    return bets


class TestRunBacktest:
    def test_basic_backtest(self):
        result = run_backtest(_bets(5, 5))
        assert result.total_bets == 10
        assert result.wins == 5
        assert result.losses == 5

    def test_all_wins_profitable(self):
        result = run_backtest(_bets(10, 0))
        assert result.total_profit > 0
        assert result.win_rate == 100.0
        assert result.grade in ("A", "B")

    def test_all_losses_negative(self):
        result = run_backtest(_bets(0, 10))
        assert result.total_profit < 0
        assert result.win_rate == 0.0
        assert result.grade == "F"

    def test_empty_bets(self):
        result = run_backtest([])
        assert result.total_bets == 0
        assert result.total_profit == 0

    def test_flat_staking(self):
        result = run_backtest(_bets(5, 5), stake_type="flat", stake_amount=50)
        assert result.avg_stake == pytest.approx(50, abs=5)

    def test_percentage_staking(self):
        result = run_backtest(_bets(5, 5), stake_type="percentage", stake_amount=5)
        assert result.total_bets == 10

    def test_kelly_staking(self):
        bets = [{"event": f"G{i}", "selection": "A", "odds_american": -110,
                 "result": "win" if i % 2 == 0 else "loss", "edge_pct": 3.0}
                for i in range(10)]
        result = run_backtest(bets, stake_type="kelly", stake_amount=100)
        assert result.total_bets == 10

    def test_min_edge_filter(self):
        bets = [
            {"event": "G1", "selection": "A", "odds_american": -110, "result": "win", "edge_pct": 5.0},
            {"event": "G2", "selection": "B", "odds_american": -110, "result": "loss", "edge_pct": 1.0},
        ]
        result = run_backtest(bets, min_edge=3.0)
        assert result.total_bets == 1

    def test_odds_filter(self):
        bets = [
            {"event": "G1", "selection": "A", "odds_american": -110, "result": "win"},
            {"event": "G2", "selection": "B", "odds_american": 500, "result": "win"},
        ]
        result = run_backtest(bets, max_odds=200)
        assert result.total_bets == 1

    def test_stop_loss(self):
        result = run_backtest(_bets(0, 100), stop_loss=9000)
        assert result.ending_bankroll >= 9000 - 200  # Should stop early

    def test_take_profit(self):
        result = run_backtest(_bets(100, 0), take_profit=11000)
        assert result.ending_bankroll <= 11100  # Should stop near target

    def test_equity_curve(self):
        result = run_backtest(_bets(5, 5))
        assert len(result.equity_curve) > 1
        assert result.equity_curve[0] == result.starting_bankroll

    def test_max_drawdown(self):
        result = run_backtest(_bets(0, 5) + _bets(5, 0))
        assert result.max_drawdown > 0

    def test_win_streak_tracking(self):
        result = run_backtest(_bets(5, 0) + _bets(0, 3))
        assert result.longest_win_streak == 5
        assert result.longest_lose_streak == 3

    def test_sharpe_ratio_calculated(self):
        result = run_backtest(_bets(5, 5))
        assert isinstance(result.sharpe_ratio, float)

    def test_profit_factor(self):
        result = run_backtest(_bets(5, 5))
        assert result.profit_factor > 0

    def test_grade_assignment(self):
        result = run_backtest(_bets(5, 5))
        assert result.grade in ("A", "B", "C", "D", "F")

    def test_push_handling(self):
        bets = [
            {"event": "G1", "selection": "A", "odds_american": -110, "result": "push"},
            {"event": "G2", "selection": "B", "odds_american": -110, "result": "win"},
        ]
        result = run_backtest(bets)
        assert result.pushes == 1
        assert result.wins == 1
