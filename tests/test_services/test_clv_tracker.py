"""Tests for the CLV tracking service."""

import pytest

from sba.services.clv_tracker import (
    calculate_clv,
    analyze_clv_history,
    _american_to_implied,
    _assess_clv,
)


class TestAmericanToImplied:
    def test_minus_110(self):
        prob = _american_to_implied(-110)
        assert 0.52 < prob < 0.53

    def test_plus_200(self):
        prob = _american_to_implied(200)
        assert abs(prob - 1/3) < 0.01

    def test_even_money(self):
        prob = _american_to_implied(100)
        assert prob == 0.5

    def test_zero_returns_half(self):
        assert _american_to_implied(0) == 0.5

    def test_heavy_favorite(self):
        prob = _american_to_implied(-300)
        assert prob == 0.75


class TestCalculateCLV:
    def test_positive_clv(self):
        """Getting -110 when line closes to -120 = positive CLV."""
        result = calculate_clv(-110, -120)
        assert result["clv_percentage"] > 0
        assert result["beat_close"] is True

    def test_negative_clv(self):
        """Getting -120 when line closes to -110 = negative CLV."""
        result = calculate_clv(-120, -110)
        assert result["clv_percentage"] < 0
        assert result["beat_close"] is False

    def test_same_odds(self):
        result = calculate_clv(-110, -110)
        assert result["clv_percentage"] == 0
        assert result["beat_close"] is False

    def test_positive_odds_clv(self):
        result = calculate_clv(200, 180)
        assert result["clv_percentage"] > 0

    def test_returns_all_fields(self):
        result = calculate_clv(-110, -115)
        assert "opening_odds" in result
        assert "closing_odds" in result
        assert "opening_implied" in result
        assert "closing_implied" in result
        assert "clv_percentage" in result
        assert "clv_american" in result
        assert "beat_close" in result
        assert "edge_assessment" in result

    def test_clv_american_diff(self):
        result = calculate_clv(-110, -120)
        assert result["clv_american"] == -10


class TestAssessCLV:
    def test_excellent(self):
        assert "Excellent" in _assess_clv(6.0)

    def test_strong(self):
        assert "Strong" in _assess_clv(3.0)

    def test_beat(self):
        assert "Beat" in _assess_clv(1.0)

    def test_close(self):
        assert "Close" in _assess_clv(-1.0)

    def test_worse(self):
        assert "Worse" in _assess_clv(-5.0)


class TestAnalyzeCLVHistory:
    def test_empty_records(self):
        result = analyze_clv_history([])
        assert result["total_bets_tracked"] == 0
        assert result["avg_clv_pct"] == 0

    def test_single_record(self):
        records = [{"clv_percentage": 2.5, "market": "h2h", "bookmaker": "FanDuel"}]
        result = analyze_clv_history(records)
        assert result["total_bets_tracked"] == 1
        assert result["avg_clv_pct"] == 2.5
        assert result["beat_close_rate"] == 100.0

    def test_mixed_records(self):
        records = [
            {"clv_percentage": 3.0, "market": "h2h", "bookmaker": "FanDuel"},
            {"clv_percentage": -1.0, "market": "spreads", "bookmaker": "DraftKings"},
            {"clv_percentage": 2.0, "market": "h2h", "bookmaker": "FanDuel"},
        ]
        result = analyze_clv_history(records)
        assert result["total_bets_tracked"] == 3
        assert result["positive_clv_bets"] == 2
        assert result["negative_clv_bets"] == 1
        assert result["best_clv"] == 3.0
        assert result["worst_clv"] == -1.0

    def test_market_breakdown(self):
        records = [
            {"clv_percentage": 3.0, "market": "h2h", "bookmaker": "A"},
            {"clv_percentage": 1.0, "market": "h2h", "bookmaker": "A"},
            {"clv_percentage": -2.0, "market": "spreads", "bookmaker": "B"},
        ]
        result = analyze_clv_history(records)
        assert "h2h" in result["by_market"]
        assert "spreads" in result["by_market"]
        assert result["by_market"]["h2h"]["avg_clv"] == 2.0

    def test_rolling_clv(self):
        records = [{"clv_percentage": i * 0.5} for i in range(10)]
        result = analyze_clv_history(records)
        assert len(result["rolling_clv"]) == 10
        assert result["rolling_clv"][0]["bet_number"] == 1

    def test_elite_assessment(self):
        records = [{"clv_percentage": 5.0} for _ in range(20)]
        result = analyze_clv_history(records)
        assert "Elite" in result["assessment"]

    def test_concerning_assessment(self):
        records = [{"clv_percentage": -5.0} for _ in range(20)]
        result = analyze_clv_history(records)
        assert "Concerning" in result["assessment"]
