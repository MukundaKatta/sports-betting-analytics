"""Tests for v2.7 improvements.

Covers:
- Sport-aware correlation lookup (fixes duplicate key bug)
- Version alignment (single source of truth)
- Async data fetching infrastructure
- OpenAPI response models
- Error handling consistency (Pydantic validators, safe_endpoint)
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app, raise_server_exceptions=False)


# ── Sport-Aware Correlations ────────────────────────────────────────


class TestSportAwareCorrelations:
    def test_nba_spread_team_win(self):
        """NBA spread/team_win should be 0.85 (was overwritten to 0.90 by NFL)."""
        from sba.services.correlations import get_correlation
        assert get_correlation("spread", "cover", "team_win", "yes", sport="nba") == 0.85

    def test_nfl_spread_team_win(self):
        """NFL spread/team_win should be 0.90."""
        from sba.services.correlations import get_correlation
        assert get_correlation("spread", "cover", "team_win", "yes", sport="nfl") == 0.90

    def test_default_sport_is_nba(self):
        """Default sport parameter should be NBA for backward compat."""
        from sba.services.correlations import get_correlation
        assert get_correlation("spread", "cover", "team_win", "yes") == 0.85

    def test_normalize_sport_api_keys(self):
        """API sport keys should map to short form."""
        from sba.services.correlations import normalize_sport
        assert normalize_sport("basketball_nba") == "nba"
        assert normalize_sport("americanfootball_nfl") == "nfl"
        assert normalize_sport("baseball_mlb") == "mlb"
        assert normalize_sport("icehockey_nhl") == "nhl"

    def test_normalize_sport_passthrough(self):
        """Already-short keys should pass through."""
        from sba.services.correlations import normalize_sport
        assert normalize_sport("nba") == "nba"
        assert normalize_sport("nfl") == "nfl"

    def test_sport_correlations_structure(self):
        """SPORT_CORRELATIONS should have separate sub-dicts per sport."""
        from sba.services.correlations import SPORT_CORRELATIONS
        assert "nba" in SPORT_CORRELATIONS
        assert "nfl" in SPORT_CORRELATIONS
        assert "mlb" in SPORT_CORRELATIONS
        assert "nhl" in SPORT_CORRELATIONS
        assert "default" in SPORT_CORRELATIONS

    def test_no_duplicate_keys_within_sport(self):
        """Each sport sub-dict should have unique keys."""
        from sba.services.correlations import SPORT_CORRELATIONS
        for sport, pairs in SPORT_CORRELATIONS.items():
            keys = list(pairs.keys())
            assert len(keys) == len(set(keys)), f"Duplicate keys in {sport}"

    def test_default_inverse_correlations(self):
        """Universal inverse pairs should be in 'default' dict."""
        from sba.services.correlations import SPORT_CORRELATIONS
        defaults = SPORT_CORRELATIONS["default"]
        assert ("player_points", "over", "player_points", "under") in defaults
        assert defaults[("player_points", "over", "player_points", "under")] == -1.0

    def test_build_sgp_with_sport(self):
        """build_sgp should accept sport parameter."""
        from sba.services.correlations import SGPLeg, build_sgp
        legs = [
            SGPLeg(market="spread", selection="Team A", direction="cover",
                   odds_american=-110, odds_decimal=1.909, implied_prob=0.524),
            SGPLeg(market="team_win", selection="Team A", direction="yes",
                   odds_american=-150, odds_decimal=1.667, implied_prob=0.6),
        ]
        nba = build_sgp(legs, sport="nba")
        nfl = build_sgp(legs, sport="nfl")
        # NFL has higher correlation (0.90 vs 0.85), so adjustment differs
        assert nba.correlation_adjustment != nfl.correlation_adjustment

    def test_correlations_api_with_sport_filter(self):
        """GET /api/correlations?sport=nba should filter results."""
        resp = client.get("/api/correlations", params={"sport": "nba"})
        assert resp.status_code == 200
        data = resp.json()
        sports = {entry["sport"] for entry in data}
        assert "nfl" not in sports
        assert "nba" in sports or "default" in sports

    def test_correlations_api_all_sports(self):
        """GET /api/correlations without sport returns all."""
        resp = client.get("/api/correlations")
        assert resp.status_code == 200
        data = resp.json()
        sports = {entry["sport"] for entry in data}
        assert len(sports) >= 4  # nba, nfl, mlb, nhl + default

    def test_sgp_calculator_accepts_sport(self):
        """POST /api/calculator/sgp should accept sport field."""
        resp = client.post("/api/calculator/sgp", json={
            "legs": [
                {"market": "spread", "selection": "Team A", "direction": "cover",
                 "odds_american": -110, "player_name": ""},
                {"market": "team_win", "selection": "Team A", "direction": "yes",
                 "odds_american": -150, "player_name": ""},
            ],
            "sport": "nfl",
            "stake": 100,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "correlated_odds_american" in data


# ── Version Alignment ───────────────────────────────────────────────


class TestVersionAlignment:
    def test_single_source_of_truth(self):
        """__version__ in sba/__init__.py should be the canonical version."""
        from sba import __version__
        assert __version__ == "2.9.0"

    def test_app_version_matches_init(self):
        """FastAPI app.version should come from sba.__version__."""
        from sba import __version__
        assert app.version == __version__

    def test_health_endpoint_version(self):
        """Health check should report the same version."""
        resp = client.get("/api/health")
        data = resp.json()
        assert data["version"] == "2.9.0"

    def test_deep_health_version(self):
        """Deep health check should report the same version."""
        resp = client.get("/api/health/deep")
        data = resp.json()
        assert data["version"] == "2.9.0"


# ── Async Data Fetching ─────────────────────────────────────────────


class TestAsyncDataFetching:
    def test_base_client_has_async_fetch(self):
        """BaseAPIClient should have async_fetch method."""
        from sba.data.clients.base import BaseAPIClient
        client_instance = BaseAPIClient(api_key="test")
        assert hasattr(client_instance, "async_fetch")
        assert asyncio.iscoroutinefunction(client_instance.async_fetch)

    def test_base_client_has_aclose(self):
        """BaseAPIClient should have aclose for cleanup."""
        from sba.data.clients.base import BaseAPIClient
        client_instance = BaseAPIClient(api_key="test")
        assert asyncio.iscoroutinefunction(client_instance.aclose)

    def test_odds_client_has_async_methods(self):
        """OddsAPIClient should expose async variants."""
        from sba.data.clients.odds_api import OddsAPIClient
        odds_client = OddsAPIClient(api_key="test")
        assert asyncio.iscoroutinefunction(odds_client.aget_sports)
        assert asyncio.iscoroutinefunction(odds_client.aget_events)
        assert asyncio.iscoroutinefunction(odds_client.aget_odds)
        assert asyncio.iscoroutinefunction(odds_client.aget_event_odds)
        assert asyncio.iscoroutinefunction(odds_client.aget_scores)

    def test_sync_fetch_still_works(self):
        """Synchronous fetch should still be available (CLI compat)."""
        from sba.data.clients.base import BaseAPIClient
        client_instance = BaseAPIClient(api_key="test")
        assert hasattr(client_instance, "fetch")
        assert not asyncio.iscoroutinefunction(client_instance.fetch)

    def test_data_syncer_has_async_methods(self):
        """DataSyncer should have async sync methods."""
        from sba.data.sync import DataSyncer
        assert hasattr(DataSyncer, "async_sync_odds")
        assert hasattr(DataSyncer, "async_sync_multi_sport")
        assert hasattr(DataSyncer, "aclose")


# ── OpenAPI Response Models ─────────────────────────────────────────


class TestOpenAPIResponseModels:
    def test_simulate_has_response_model(self):
        """POST /simulate should have a typed response."""
        resp = client.post("/api/simulate", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "percentiles" in data
        assert "summary" in data
        assert "p10" in data["percentiles"]
        assert "median_final" in data["summary"]

    def test_backtest_has_response_model(self):
        """POST /backtest should have a typed response."""
        resp = client.post("/api/backtest", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "strategy_name" in data
        assert "grade" in data
        assert "total_bets" in data
        assert "equity_curve" in data

    def test_bankroll_has_response_model(self):
        """GET /bankroll should have a typed response."""
        resp = client.get("/api/bankroll")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_balance" in data
        assert "roi_pct" in data
        assert "history" in data

    def test_clv_summary_has_response_model(self):
        """GET /clv/summary should have a typed response."""
        resp = client.get("/api/clv/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_tracked" in data
        assert "avg_clv" in data
        assert "entries" in data

    def test_bankroll_daily_has_response_model(self):
        """GET /bankroll/daily should return a typed list."""
        resp = client.get("/api/bankroll/daily")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ── Error Handling ──────────────────────────────────────────────────


class TestErrorHandling:
    def test_simulation_pydantic_validation(self):
        """Invalid win_rate should be caught by Pydantic, not manual check."""
        resp = client.post("/api/simulate", json={"win_rate": 1.5})
        assert resp.status_code == 422

    def test_simulation_invalid_bankroll(self):
        """Bankroll <= 0 should fail validation."""
        resp = client.post("/api/simulate", json={"bankroll": -100})
        assert resp.status_code == 422

    def test_simulation_invalid_kelly(self):
        """Kelly fraction > 1 should fail validation."""
        resp = client.post("/api/simulate", json={"kelly_fraction": 2.0})
        assert resp.status_code == 422

    def test_safe_endpoint_decorator_exists(self):
        """safe_endpoint and safe_async_endpoint should be importable."""
        from sba.web.errors import safe_endpoint, safe_async_endpoint
        assert callable(safe_endpoint)
        assert callable(safe_async_endpoint)

    def test_service_unavailable_error(self):
        """ServiceUnavailableError should produce 503."""
        from sba.web.errors import ServiceUnavailableError
        err = ServiceUnavailableError("Database")
        assert err.status_code == 503
        assert "Database" in err.message

    def test_bankroll_error_handling(self):
        """Bankroll endpoints should handle errors via safe_endpoint."""
        # Deposit with valid data should work
        resp = client.post("/api/bankroll/deposit", json={"amount": 100})
        assert resp.status_code == 200


# ── Version ──────────────────────────────────────────────────────────


class TestVersion:
    def test_version_bumped(self):
        assert app.version == "2.9.0"
