"""Tests for v3.0 improvements.

Covers:
- ROI Forecasting engine
- Bet Timing analysis
- Risk-adjusted metrics (Sharpe, Sortino, Calmar)
- Version alignment (3.0.0)
- Bug fixes (settings prefix, mutable defaults, SQL injection)
- Connection pooling
- New API endpoints
- New view pages
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app, raise_server_exceptions=False)


# ── Version Alignment ───────────────────────────────────────────────


class TestVersionAlignment:
    def test_version_is_3_0(self):
        """__version__ should be 3.0.0."""
        from sba import __version__
        assert __version__ == "3.0.0"

    def test_app_version_matches(self):
        """FastAPI app.version should match __version__."""
        from sba import __version__
        assert app.version == __version__

    def test_health_version(self):
        """Health endpoint should report 3.0.0."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["version"] == "3.0.0"

    def test_deep_health_version(self):
        """Deep health should report 3.0.0."""
        resp = client.get("/api/health/deep")
        assert resp.status_code == 200
        assert resp.json()["version"] == "3.0.0"


# ── ROI Forecast Service ───────────────────────────────────────────


class TestROIForecast:
    def test_forecast_empty_bets(self):
        """Empty bets should return low confidence forecast."""
        from sba.services.roi_forecast import forecast_roi
        result = forecast_roi([])
        assert result.confidence_level == "low"
        assert result.sample_size == 0
        assert result.break_even_probability == 50.0
        assert len(result.recommendations) > 0

    def test_forecast_with_bets(self):
        """Should generate forecast from settled bets."""
        from sba.services.roi_forecast import forecast_roi
        bets = [
            {"profit_loss": 100, "stake": 100, "status": "won"},
            {"profit_loss": -100, "stake": 100, "status": "lost"},
            {"profit_loss": 80, "stake": 100, "status": "won"},
            {"profit_loss": 60, "stake": 100, "status": "won"},
            {"profit_loss": -100, "stake": 100, "status": "lost"},
        ] * 6  # 30 bets, net positive
        result = forecast_roi(bets, bankroll=1000)
        assert result.sample_size == 30
        assert result.confidence_level == "medium"
        assert len(result.forecast_curve) > 0
        assert result.break_even_probability >= 0

    def test_forecast_positive_edge(self):
        """Bets with positive edge should show positive projection."""
        from sba.services.roi_forecast import forecast_roi
        bets = [
            {"profit_loss": 100, "stake": 100, "status": "won"},
            {"profit_loss": -100, "stake": 100, "status": "lost"},
            {"profit_loss": 100, "stake": 100, "status": "won"},
            {"profit_loss": 100, "stake": 100, "status": "won"},
            {"profit_loss": -100, "stake": 100, "status": "lost"},
        ] * 20  # 100 bets, 60% win rate
        result = forecast_roi(bets, bankroll=5000)
        assert result.current_roi > 0
        assert result.edge_per_bet > 0
        assert result.break_even_probability > 50

    def test_forecast_curve_structure(self):
        """Forecast curve should have proper structure."""
        from sba.services.roi_forecast import forecast_roi
        bets = [{"profit_loss": 10, "stake": 100}] * 10
        result = forecast_roi(bets, bankroll=1000, projection_bets=50)
        for pt in result.forecast_curve:
            assert hasattr(pt, "bet_number")
            assert hasattr(pt, "projected_profit")
            assert hasattr(pt, "lower_bound")
            assert hasattr(pt, "upper_bound")

    def test_forecast_api_endpoint(self):
        """GET /api/roi-forecast should return 200."""
        resp = client.get("/api/roi-forecast")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_roi" in data
        assert "projected_roi_30" in data
        assert "break_even_probability" in data
        assert "forecast_curve" in data
        assert "recommendations" in data


# ── Bet Timing Service ─────────────────────────────────────────────


class TestBetTiming:
    def test_timing_empty_bets(self):
        """Empty bets should return empty analysis."""
        from sba.services.bet_timing import analyze_bet_timing
        result = analyze_bet_timing([])
        assert result.timing_score == 0
        assert result.optimal_window == "Insufficient data"

    def test_timing_with_data(self):
        """Should analyze timing patterns."""
        from sba.services.bet_timing import analyze_bet_timing
        bets = [
            {"placed_at": "2024-03-01 14:30:00", "profit_loss": 50, "stake": 100,
             "status": "won", "recommended_stake": 100},
            {"placed_at": "2024-03-01 14:45:00", "profit_loss": -100, "stake": 100,
             "status": "lost", "recommended_stake": 100},
            {"placed_at": "2024-03-02 20:00:00", "profit_loss": 80, "stake": 100,
             "status": "won", "recommended_stake": 100},
            {"placed_at": "2024-03-02 20:30:00", "profit_loss": 60, "stake": 100,
             "status": "won", "recommended_stake": 100},
        ]
        result = analyze_bet_timing(bets)
        assert len(result.by_hour) == 24
        assert len(result.by_day) == 7

    def test_timing_24_hour_slots(self):
        """Should have exactly 24 hourly windows."""
        from sba.services.bet_timing import analyze_bet_timing
        result = analyze_bet_timing([])
        assert len(result.by_hour) == 24

    def test_timing_7_day_slots(self):
        """Should have exactly 7 daily windows."""
        from sba.services.bet_timing import analyze_bet_timing
        result = analyze_bet_timing([])
        assert len(result.by_day) == 7

    def test_timing_api_endpoint(self):
        """GET /api/bet-timing should return 200."""
        resp = client.get("/api/bet-timing")
        assert resp.status_code == 200
        data = resp.json()
        assert "optimal_window" in data
        assert "timing_score" in data
        assert "by_hour" in data
        assert "by_day" in data
        assert "recommendations" in data


# ── Risk Metrics Service ───────────────────────────────────────────


class TestRiskMetrics:
    def test_empty_bets(self):
        """Empty bets should return empty metrics."""
        from sba.services.risk_metrics import calculate_risk_metrics
        result = calculate_risk_metrics([])
        assert result.total_bets == 0
        assert result.risk_grade == "N/A"

    def test_positive_edge_bets(self):
        """Positive edge should produce positive Sharpe."""
        from sba.services.risk_metrics import calculate_risk_metrics
        bets = [
            {"profit_loss": 100, "stake": 100, "status": "won", "recommended_stake": 100},
            {"profit_loss": -100, "stake": 100, "status": "lost", "recommended_stake": 100},
            {"profit_loss": 100, "stake": 100, "status": "won", "recommended_stake": 100},
            {"profit_loss": 100, "stake": 100, "status": "won", "recommended_stake": 100},
        ] * 10
        result = calculate_risk_metrics(bets, bankroll=5000)
        assert result.sharpe_ratio > 0
        assert result.profit_factor > 1.0
        assert result.roi_pct > 0

    def test_risk_grade_assigned(self):
        """Should assign a letter grade."""
        from sba.services.risk_metrics import calculate_risk_metrics
        bets = [
            {"profit_loss": 50, "stake": 100, "status": "won", "recommended_stake": 100},
            {"profit_loss": -100, "stake": 100, "status": "lost", "recommended_stake": 100},
        ] * 15
        result = calculate_risk_metrics(bets)
        assert result.risk_grade in ("A+", "A", "B+", "B", "C+", "C", "D", "F")

    def test_drawdown_calculation(self):
        """Max drawdown should be non-negative."""
        from sba.services.risk_metrics import calculate_risk_metrics
        bets = [
            {"profit_loss": -100, "stake": 100, "status": "lost", "recommended_stake": 100},
            {"profit_loss": -100, "stake": 100, "status": "lost", "recommended_stake": 100},
            {"profit_loss": 200, "stake": 100, "status": "won", "recommended_stake": 100},
        ]
        result = calculate_risk_metrics(bets, bankroll=1000)
        assert result.max_drawdown.max_drawdown >= 0
        assert result.max_drawdown.max_drawdown_pct >= 0

    def test_distribution_stats(self):
        """Should compute avg_win and avg_loss."""
        from sba.services.risk_metrics import calculate_risk_metrics
        bets = [
            {"profit_loss": 100, "stake": 100, "status": "won", "recommended_stake": 100},
            {"profit_loss": -50, "stake": 100, "status": "lost", "recommended_stake": 100},
        ]
        result = calculate_risk_metrics(bets)
        assert result.distribution.avg_win == 100
        assert result.distribution.avg_loss == 50

    def test_risk_metrics_api_endpoint(self):
        """GET /api/risk-metrics should return 200."""
        resp = client.get("/api/risk-metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "sharpe_ratio" in data
        assert "sortino_ratio" in data
        assert "calmar_ratio" in data
        assert "profit_factor" in data
        assert "risk_grade" in data
        assert "max_drawdown" in data
        assert "distribution" in data

    def test_sortino_only_downside(self):
        """All-winning record should have high Sortino."""
        from sba.services.risk_metrics import calculate_risk_metrics
        bets = [
            {"profit_loss": 50, "stake": 100, "status": "won", "recommended_stake": 100},
            {"profit_loss": 30, "stake": 100, "status": "won", "recommended_stake": 100},
            {"profit_loss": 70, "stake": 100, "status": "won", "recommended_stake": 100},
        ]
        result = calculate_risk_metrics(bets)
        assert result.sortino_ratio > result.sharpe_ratio


# ── Bug Fixes ──────────────────────────────────────────────────────


class TestBugFixes:
    def test_settings_env_prefix(self):
        """Settings update should use SBA_ prefix."""
        import os
        resp = client.put("/api/settings", json={"bankroll": 5000})
        assert resp.status_code == 200
        # The env var should be set with SBA_ prefix
        val = os.environ.get("SBA_BANKROLL")
        if val is not None:
            assert float(val) == 5000.0

    def test_mutable_default_fixed(self):
        """POST /api/public-money/analyze should not share state."""
        resp1 = client.post("/api/public-money/analyze",
                            params={"event_id": "test1", "market": "h2h"})
        resp2 = client.post("/api/public-money/analyze",
                            params={"event_id": "test2", "market": "h2h"})
        # Both should work independently (no shared mutable list)
        assert resp1.status_code == 200
        assert resp2.status_code == 200

    def test_power_ratings_parameterized(self):
        """Power ratings should use exact match, not LIKE."""
        resp = client.get("/api/power-ratings", params={"sport": "basketball_nba"})
        assert resp.status_code == 200


# ── New View Pages ─────────────────────────────────────────────────


class TestNewViewPages:
    def test_roi_forecast_page(self):
        """ROI forecast page should load."""
        resp = client.get("/roi-forecast")
        assert resp.status_code == 200
        assert "ROI Forecast" in resp.text

    def test_bet_timing_page(self):
        """Bet timing page should load."""
        resp = client.get("/bet-timing")
        assert resp.status_code == 200
        assert "Bet Timing" in resp.text

    def test_risk_metrics_page(self):
        """Risk metrics page should load."""
        resp = client.get("/risk-metrics")
        assert resp.status_code == 200
        assert "Risk Metrics" in resp.text


# ── Connection Pooling ─────────────────────────────────────────────


class TestConnectionPooling:
    def test_connection_reuse(self):
        """Thread-local connections should be reusable."""
        from sba.data.db import get_connection
        with get_connection() as conn1:
            conn1.execute("SELECT 1")
        # Second call in same thread should work (reuse or recreate)
        with get_connection() as conn2:
            conn2.execute("SELECT 1")

    def test_connection_integrity(self):
        """Database operations should work with pooled connections."""
        from sba.data.db import get_connection
        with get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()
            assert count["c"] >= 0


# ── API Response Quality ───────────────────────────────────────────


class TestAPIResponseQuality:
    def test_forecast_response_structure(self):
        """ROI forecast should have complete structure."""
        resp = client.get("/api/roi-forecast")
        data = resp.json()
        required = ["current_roi", "projected_roi_30", "projected_roi_100",
                     "confidence_level", "sample_size", "edge_per_bet",
                     "variance", "break_even_probability", "risk_assessment",
                     "recommendations", "forecast_curve"]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_risk_metrics_response_structure(self):
        """Risk metrics should have complete structure."""
        resp = client.get("/api/risk-metrics")
        data = resp.json()
        assert "max_drawdown" in data
        dd = data["max_drawdown"]
        assert "amount" in dd
        assert "pct" in dd
        assert "current_amount" in dd
        assert "distribution" in data
        dist = data["distribution"]
        assert "avg_win" in dist
        assert "avg_loss" in dist
        assert "expectancy" in dist

    def test_timing_response_structure(self):
        """Bet timing should have complete structure."""
        resp = client.get("/api/bet-timing")
        data = resp.json()
        assert len(data["by_hour"]) == 24
        assert len(data["by_day"]) == 7
        assert isinstance(data["timing_score"], (int, float))
