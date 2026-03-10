"""Tests for the analytics service."""

from datetime import datetime

import pytest

from sba.services.analytics import (
    BreakdownRow,
    StreakInfo,
    TrendPoint,
    analyze_streaks,
    breakdown_by_bookmaker,
    breakdown_by_day_of_week,
    breakdown_by_market,
    breakdown_by_odds_range,
    breakdown_by_sport,
    performance_heatmap,
    rolling_trends,
)


def _bet(status="won", sport="basketball_nba", market="h2h", bookmaker="fanduel",
         odds=-150, stake=100, profit=66.67, placed_at=None):
    return {
        "status": status,
        "sport": sport,
        "market": market,
        "bookmaker": bookmaker,
        "odds_american": odds,
        "stake": stake,
        "profit_loss": profit if status in ("won", "win") else -stake,
        "placed_at": placed_at or datetime(2025, 3, 15, 14, 0),
    }


def _sample_bets():
    """A diverse set of bets for testing breakdowns."""
    return [
        _bet(status="won", sport="basketball_nba", market="h2h", bookmaker="fanduel",
             odds=-150, stake=100, profit=66.67,
             placed_at=datetime(2025, 3, 10, 14, 0)),  # Monday
        _bet(status="lost", sport="basketball_nba", market="spreads", bookmaker="draftkings",
             odds=-110, stake=50, profit=-50,
             placed_at=datetime(2025, 3, 11, 18, 0)),  # Tuesday
        _bet(status="won", sport="americanfootball_nfl", market="h2h", bookmaker="fanduel",
             odds=200, stake=50, profit=100,
             placed_at=datetime(2025, 3, 12, 20, 0)),  # Wednesday
        _bet(status="lost", sport="americanfootball_nfl", market="totals", bookmaker="betmgm",
             odds=-110, stake=100, profit=-100,
             placed_at=datetime(2025, 3, 13, 10, 0)),  # Thursday
        _bet(status="won", sport="basketball_nba", market="h2h", bookmaker="fanduel",
             odds=-130, stake=75, profit=57.69,
             placed_at=datetime(2025, 3, 14, 19, 0)),  # Friday
    ]


class TestBreakdownBySport:
    def test_groups_by_sport(self):
        bets = _sample_bets()
        rows = breakdown_by_sport(bets)
        labels = {r.label for r in rows}
        assert "basketball_nba" in labels
        assert "americanfootball_nfl" in labels

    def test_counts_correct(self):
        bets = _sample_bets()
        rows = breakdown_by_sport(bets)
        nba = next(r for r in rows if r.label == "basketball_nba")
        assert nba.bets == 3
        assert nba.wins == 2
        assert nba.losses == 1

    def test_empty_input(self):
        assert breakdown_by_sport([]) == []

    def test_sorted_by_profit_desc(self):
        bets = _sample_bets()
        rows = breakdown_by_sport(bets)
        profits = [r.profit for r in rows]
        assert profits == sorted(profits, reverse=True)


class TestBreakdownByDayOfWeek:
    def test_returns_seven_days(self):
        bets = _sample_bets()
        rows = breakdown_by_day_of_week(bets)
        assert len(rows) == 7
        assert rows[0].label == "Monday"
        assert rows[6].label == "Sunday"

    def test_monday_has_one_bet(self):
        bets = _sample_bets()
        rows = breakdown_by_day_of_week(bets)
        monday = rows[0]
        assert monday.bets == 1
        assert monday.wins == 1

    def test_empty_days_have_zero_bets(self):
        bets = _sample_bets()
        rows = breakdown_by_day_of_week(bets)
        saturday = rows[5]
        assert saturday.bets == 0

    def test_string_dates_parsed(self):
        bets = [_bet(placed_at="2025-03-10T14:00:00")]
        rows = breakdown_by_day_of_week(bets)
        monday = rows[0]
        assert monday.bets == 1


class TestBreakdownByOddsRange:
    def test_buckets_correctly(self):
        bets = _sample_bets()
        rows = breakdown_by_odds_range(bets)
        labels = {r.label for r in rows}
        assert "Moderate Favorite" in labels or "Slight Favorite" in labels

    def test_empty_input(self):
        assert breakdown_by_odds_range([]) == []

    def test_underdog_bucket(self):
        bets = [_bet(odds=200)]
        rows = breakdown_by_odds_range(bets)
        assert len(rows) == 1
        assert rows[0].label == "Moderate Underdog"


class TestBreakdownByMarket:
    def test_groups_by_market(self):
        bets = _sample_bets()
        rows = breakdown_by_market(bets)
        labels = {r.label for r in rows}
        assert "h2h" in labels
        assert "spreads" in labels
        assert "totals" in labels

    def test_h2h_count(self):
        bets = _sample_bets()
        rows = breakdown_by_market(bets)
        h2h = next(r for r in rows if r.label == "h2h")
        assert h2h.bets == 3


class TestBreakdownByBookmaker:
    def test_groups_by_bookmaker(self):
        bets = _sample_bets()
        rows = breakdown_by_bookmaker(bets)
        labels = {r.label for r in rows}
        assert "fanduel" in labels
        assert "draftkings" in labels
        assert "betmgm" in labels

    def test_fanduel_count(self):
        bets = _sample_bets()
        rows = breakdown_by_bookmaker(bets)
        fd = next(r for r in rows if r.label == "fanduel")
        assert fd.bets == 3


class TestRollingTrends:
    def test_returns_trend_points(self):
        bets = _sample_bets()
        points = rolling_trends(bets)
        assert len(points) == 5  # 5 distinct dates
        assert all(isinstance(p, TrendPoint) for p in points)

    def test_cumulative_profit(self):
        bets = _sample_bets()
        points = rolling_trends(bets)
        # Cumulative should be running total
        assert points[0].cumulative == points[0].profit
        assert points[-1].cumulative == pytest.approx(
            sum(p.profit for p in points), abs=0.1
        )

    def test_empty_input(self):
        assert rolling_trends([]) == []

    def test_string_dates(self):
        bets = [_bet(placed_at="2025-03-10T14:00:00")]
        points = rolling_trends(bets)
        assert len(points) == 1
        assert points[0].date == "2025-03-10"


class TestAnalyzeStreaks:
    def test_win_streak(self):
        bets = [_bet(status="won") for _ in range(5)]
        info = analyze_streaks(bets)
        assert info.current_type == "win"
        assert info.current_length == 5
        assert info.longest_win == 5

    def test_loss_streak(self):
        bets = [_bet(status="lost") for _ in range(3)]
        info = analyze_streaks(bets)
        assert info.current_type == "loss"
        assert info.current_length == 3
        assert info.longest_loss == 3

    def test_mixed_streaks(self):
        bets = [
            _bet(status="won"), _bet(status="won"), _bet(status="won"),
            _bet(status="lost"), _bet(status="lost"),
            _bet(status="won"),
        ]
        info = analyze_streaks(bets)
        assert info.longest_win == 3
        assert info.longest_loss == 2
        assert info.current_type == "win"
        assert info.current_length == 1

    def test_empty_input(self):
        info = analyze_streaks([])
        assert info.current_type == "none"
        assert info.current_length == 0

    def test_returns_streak_info(self):
        bets = _sample_bets()
        info = analyze_streaks(bets)
        assert isinstance(info, StreakInfo)


class TestPerformanceHeatmap:
    def test_returns_entries(self):
        bets = _sample_bets()
        result = performance_heatmap(bets)
        assert len(result) > 0
        assert all("day" in r and "hour" in r for r in result)

    def test_entry_fields(self):
        bets = _sample_bets()
        result = performance_heatmap(bets)
        entry = result[0]
        assert "bets" in entry
        assert "profit" in entry
        assert "win_rate" in entry
        assert "day_num" in entry

    def test_empty_input(self):
        assert performance_heatmap([]) == []


class TestComputeRow:
    def test_win_rate_calculation(self):
        bets = [_bet(status="won"), _bet(status="won"), _bet(status="lost")]
        rows = breakdown_by_sport(bets)
        assert rows[0].win_rate == pytest.approx(66.7, abs=0.1)

    def test_roi_calculation(self):
        bets = [_bet(status="won", stake=100, profit=66.67)]
        rows = breakdown_by_sport(bets)
        assert rows[0].roi_pct == pytest.approx(66.7, abs=0.1)

    def test_push_handling(self):
        bets = [_bet(status="push")]
        # Profit_loss for push defaults to -stake in our helper, fix it
        bets[0]["profit_loss"] = 0
        bets[0]["stake"] = 100
        rows = breakdown_by_sport(bets)
        assert rows[0].pushes == 1
        assert rows[0].wins == 0
        assert rows[0].losses == 0
