"""Tests for Variance Simulator, Filter Presets, and Expected vs Actual API endpoints."""

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app)


class TestVarianceSimulator:
    def test_basic_simulation(self):
        resp = client.post("/api/simulator/variance", json={
            "win_rate": 0.55,
            "avg_odds_decimal": 1.91,
            "bankroll": 1000,
            "num_bets": 100,
            "num_simulations": 200,
            "stake_pct": 2.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "parameters" in data
        assert "results" in data
        assert "drawdown" in data
        assert "percentile_curves" in data
        assert "assessment" in data

    def test_results_structure(self):
        resp = client.post("/api/simulator/variance", json={
            "win_rate": 0.55,
            "num_bets": 50,
            "num_simulations": 100,
        })
        data = resp.json()
        results = data["results"]
        assert "median_final" in results
        assert "bust_rate" in results
        assert "profit_probability" in results
        assert results["profit_probability"] >= 0
        assert results["profit_probability"] <= 100

    def test_negative_ev_high_bust(self):
        resp = client.post("/api/simulator/variance", json={
            "win_rate": 0.40,
            "avg_odds_decimal": 1.91,
            "bankroll": 1000,
            "num_bets": 500,
            "num_simulations": 200,
            "stake_pct": 5.0,
        })
        data = resp.json()
        assert "Negative expected value" in data["assessment"]

    def test_percentile_curves(self):
        resp = client.post("/api/simulator/variance", json={
            "win_rate": 0.55,
            "num_bets": 100,
            "num_simulations": 100,
        })
        curves = resp.json()["percentile_curves"]
        assert len(curves["bet_numbers"]) == 20
        assert len(curves["p50"]) == 20
        # P95 should be above P5
        assert curves["p95"][-1] >= curves["p5"][-1]

    def test_invalid_win_rate(self):
        resp = client.post("/api/simulator/variance", json={
            "win_rate": 1.5,
        })
        assert resp.status_code == 422

    def test_invalid_num_bets(self):
        resp = client.post("/api/simulator/variance", json={
            "num_bets": 0,
        })
        assert resp.status_code == 422


class TestFilterPresets:
    def test_save_and_get_preset(self):
        # Save
        resp = client.post("/api/presets", json={
            "name": "Test Preset NBA",
            "filters": {"sport": "basketball_nba", "min_ev": 3, "market": "h2h"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        assert data["name"] == "Test Preset NBA"

        # Get all
        resp = client.get("/api/presets")
        assert resp.status_code == 200
        presets = resp.json()["presets"]
        assert any(p["name"] == "Test Preset NBA" for p in presets)

    def test_delete_preset(self):
        # Save first
        client.post("/api/presets", json={
            "name": "To Delete",
            "filters": {"sport": "nfl"},
        })

        # Delete
        resp = client.delete("/api/presets/preset_to_delete")
        assert resp.status_code == 200

    def test_delete_nonexistent(self):
        resp = client.delete("/api/presets/preset_nonexistent_xyz")
        assert resp.status_code == 404

    def test_empty_name_rejected(self):
        resp = client.post("/api/presets", json={
            "name": "",
            "filters": {},
        })
        assert resp.status_code == 422

    def test_overwrite_preset(self):
        """Saving a preset with the same name should overwrite."""
        client.post("/api/presets", json={
            "name": "Overwrite Test",
            "filters": {"v": 1},
        })
        client.post("/api/presets", json={
            "name": "Overwrite Test",
            "filters": {"v": 2},
        })
        resp = client.get("/api/presets")
        matching = [p for p in resp.json()["presets"] if p["name"] == "Overwrite Test"]
        assert len(matching) == 1
        assert matching[0]["filters"]["v"] == 2


class TestExplainBet:
    def test_basic_explain(self):
        resp = client.post("/api/explain", json={
            "odds_american": -110,
            "model_probability": 0.55,
            "ev_pct": 3.5,
            "kelly_fraction": 0.03,
            "clv_pct": 2.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "rating" in data
        assert "factors" in data
        assert "strengths" in data
        assert "warnings" in data
        assert "confidence" in data
        assert "recommendation" in data

    def test_high_confidence_with_all_factors(self):
        resp = client.post("/api/explain", json={
            "odds_american": -110,
            "model_probability": 0.60,
            "ev_pct": 8.0,
            "kelly_fraction": 0.05,
            "clv_pct": 4.0,
        })
        data = resp.json()
        assert data["confidence"] == "high"
        assert len(data["strengths"]) >= 2

    def test_minimal_input(self):
        resp = client.post("/api/explain", json={
            "odds_american": 150,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["confidence"] == "low"
        assert len(data["factors"]) >= 2  # odds + market context at minimum

    def test_negative_signals(self):
        resp = client.post("/api/explain", json={
            "odds_american": -200,
            "ev_pct": -3.0,
            "kelly_fraction": 0,
            "clv_pct": -5.0,
        })
        data = resp.json()
        assert len(data["warnings"]) >= 2

    def test_factors_have_structure(self):
        resp = client.post("/api/explain", json={
            "odds_american": -110,
            "ev_pct": 5.0,
        })
        data = resp.json()
        for f in data["factors"]:
            assert "category" in f
            assert "factor" in f
            assert "impact" in f
            assert "explanation" in f


class TestExpectedVsActual:
    def test_returns_200(self):
        resp = client.get("/api/performance/expected-vs-actual")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_bets" in data
        assert "expected_profit" in data
        assert "actual_profit" in data
        assert "assessment" in data

    def test_has_breakdown(self):
        resp = client.get("/api/performance/expected-vs-actual")
        data = resp.json()
        assert "by_month" in data
        assert "by_market" in data
        assert "cumulative" in data
