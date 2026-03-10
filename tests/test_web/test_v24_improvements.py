"""Tests for v2.4 improvements.

Covers:
- Extracted CLV routes
- Extracted simulation/backtest routes
- Multi-sport SGP correlation engine with conflict detection
- Thread-safe bounded TTL cache
- RequestID middleware
- Rate limiter with proxy support and memory bounds
- Settings-based CORS and rate limit configuration
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app, raise_server_exceptions=False)


# ── Extracted CLV Routes ─────────────────────────────────────────────


class TestCLVRoutes:
    def test_clv_summary(self):
        resp = client.get("/api/clv/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_tracked" in data
        assert "avg_clv" in data
        assert "clv_by_market" in data
        assert "clv_by_bookmaker" in data

    def test_clv_record_missing_bet(self):
        resp = client.post("/api/clv/record", json={
            "bet_id": 999999,
            "closing_odds_american": -105,
        })
        assert resp.status_code == 404

    def test_clv_record_invalid_body(self):
        resp = client.post("/api/clv/record", json={})
        assert resp.status_code == 422


# ── Extracted Simulation Routes ──────────────────────────────────────


class TestSimulationRoutes:
    def test_simulate_default(self):
        resp = client.post("/api/simulate", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "percentiles" in data
        assert "summary" in data
        for key in ("p10", "p25", "p50", "p75", "p90"):
            assert key in data["percentiles"]
        assert "median_final" in data["summary"]
        assert "profitable_pct" in data["summary"]

    def test_simulate_custom_params(self):
        resp = client.post("/api/simulate", json={
            "bankroll": 5000,
            "num_bets": 50,
            "avg_odds": 100,
            "win_rate": 0.55,
            "kelly_fraction": 0.15,
            "simulations": 20,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulations"] == 20
        assert data["num_bets"] == 50

    def test_simulate_invalid_win_rate(self):
        resp = client.post("/api/simulate", json={"win_rate": 1.5})
        assert resp.status_code == 422

    def test_simulate_invalid_bankroll(self):
        resp = client.post("/api/simulate", json={"bankroll": -100})
        assert resp.status_code == 422

    def test_backtest_default(self):
        resp = client.post("/api/backtest", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "total_bets" in data
        assert "win_rate" in data
        assert "roi_pct" in data
        assert "equity_curve" in data
        assert "grade" in data

    def test_backtest_custom_strategy(self):
        resp = client.post("/api/backtest", json={
            "strategy_name": "Test Strategy",
            "starting_bankroll": 5000,
            "stake_type": "flat",
            "stake_amount": 50,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy_name"] == "Test Strategy"
        assert data["starting_bankroll"] == 5000


# ── Multi-Sport SGP Correlation Engine ───────────────────────────────


class TestCorrelationEngine:
    def test_nba_correlations_exist(self):
        from sba.services.correlations import CORRELATION_MATRIX
        key = ("player_points", "over", "player_threes", "over")
        assert key in CORRELATION_MATRIX
        assert CORRELATION_MATRIX[key] == 0.45

    def test_nfl_correlations_exist(self):
        from sba.services.correlations import CORRELATION_MATRIX
        key = ("qb_passing_yards", "over", "qb_passing_tds", "over")
        assert key in CORRELATION_MATRIX
        assert CORRELATION_MATRIX[key] == 0.55

    def test_mlb_correlations_exist(self):
        from sba.services.correlations import CORRELATION_MATRIX
        key = ("batter_home_runs", "over", "batter_rbis", "over")
        assert key in CORRELATION_MATRIX
        assert CORRELATION_MATRIX[key] == 0.50

    def test_nhl_correlations_exist(self):
        from sba.services.correlations import CORRELATION_MATRIX
        key = ("player_goals", "over", "player_points_nhl", "over")
        assert key in CORRELATION_MATRIX
        assert CORRELATION_MATRIX[key] == 0.70

    def test_get_correlation_direct(self):
        from sba.services.correlations import get_correlation
        assert get_correlation("player_points", "over", "player_threes", "over") == 0.45

    def test_get_correlation_reverse_lookup(self):
        from sba.services.correlations import get_correlation
        # The matrix has (player_points, over, player_assists, over) = 0.15
        assert get_correlation("player_assists", "over", "player_points", "over") == 0.15

    def test_get_correlation_unknown_defaults_zero(self):
        from sba.services.correlations import get_correlation
        assert get_correlation("unknown_market", "over", "other_market", "over") == 0.0

    def test_get_correlation_same_player_default(self):
        from sba.services.correlations import get_correlation
        # Same player props with no explicit entry get 0.05
        assert get_correlation("player_foo", "over", "player_bar", "over") == 0.05

    def test_conflict_detection(self):
        from sba.services.correlations import SGPLeg, check_conflicts
        legs = [
            SGPLeg(market="player_points", selection="pts", direction="over",
                   odds_american=-110, odds_decimal=1.909, implied_prob=0.524,
                   player_name="LeBron"),
            SGPLeg(market="player_points", selection="pts", direction="under",
                   odds_american=-110, odds_decimal=1.909, implied_prob=0.524,
                   player_name="LeBron"),
        ]
        conflicts = check_conflicts(legs)
        assert len(conflicts) >= 1
        assert "Conflict" in conflicts[0]

    def test_no_conflict_compatible_legs(self):
        from sba.services.correlations import SGPLeg, check_conflicts
        legs = [
            SGPLeg(market="player_points", selection="pts", direction="over",
                   odds_american=-110, odds_decimal=1.909, implied_prob=0.524,
                   player_name="LeBron"),
            SGPLeg(market="player_assists", selection="ast", direction="over",
                   odds_american=-110, odds_decimal=1.909, implied_prob=0.524,
                   player_name="Curry"),
        ]
        conflicts = check_conflicts(legs)
        assert len(conflicts) == 0

    def test_build_sgp_linked_tags(self):
        from sba.services.correlations import SGPLeg, build_sgp
        legs = [
            SGPLeg(market="player_points", selection="pts", direction="over",
                   odds_american=-110, odds_decimal=1.909, implied_prob=0.524,
                   player_name="LeBron"),
            SGPLeg(market="player_threes", selection="3pm", direction="over",
                   odds_american=120, odds_decimal=2.2, implied_prob=0.455,
                   player_name="LeBron"),
        ]
        analysis = build_sgp(legs)
        assert analysis.naive_probability > 0
        assert analysis.correlated_probability > 0
        assert analysis.correlation_adjustment != 0
        # Should have LINKED tag for 0.45 correlation
        linked = [c for c in analysis.correlations if c["tag"] == "LINKED"]
        assert len(linked) >= 1

    def test_build_sgp_minimum_legs(self):
        from sba.services.correlations import SGPLeg, build_sgp
        leg = SGPLeg(market="player_points", selection="pts", direction="over",
                     odds_american=-110, odds_decimal=1.909, implied_prob=0.524)
        with pytest.raises(ValueError, match="at least 2 legs"):
            build_sgp([leg])


# ── Thread-Safe Bounded TTL Cache ────────────────────────────────────


class TestTTLCache:
    def test_basic_set_get(self):
        from sba.utils.cache import TTLCache
        c = TTLCache(max_entries=10)
        c.set("key1", "value1", ttl=10)
        assert c.get("key1") == "value1"

    def test_ttl_expiry(self):
        from sba.utils.cache import TTLCache
        c = TTLCache(max_entries=10)
        c.set("key1", "value1", ttl=0.05)
        time.sleep(0.06)
        assert c.get("key1") is None

    def test_max_entries_eviction(self):
        from sba.utils.cache import TTLCache
        c = TTLCache(max_entries=5)
        for i in range(10):
            c.set(f"key{i}", f"val{i}", ttl=60)
        assert c.stats["entries"] <= 5

    def test_invalidate_all(self):
        from sba.utils.cache import TTLCache
        c = TTLCache(max_entries=10)
        c.set("a", 1, ttl=60)
        c.set("b", 2, ttl=60)
        c.invalidate()
        assert c.get("a") is None
        assert c.get("b") is None

    def test_invalidate_prefix(self):
        from sba.utils.cache import TTLCache
        c = TTLCache(max_entries=10)
        c.set("sports:nba", 1, ttl=60)
        c.set("sports:nfl", 2, ttl=60)
        c.set("odds:main", 3, ttl=60)
        c.invalidate("sports:")
        assert c.get("sports:nba") is None
        assert c.get("sports:nfl") is None
        assert c.get("odds:main") == 3

    def test_stats(self):
        from sba.utils.cache import TTLCache
        c = TTLCache(max_entries=100)
        c.set("x", 1, ttl=60)
        c.get("x")  # hit
        c.get("y")  # miss
        stats = c.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["entries"] == 1
        assert stats["max_entries"] == 100
        assert stats["hit_rate"] == 50.0

    def test_thread_safety(self):
        from sba.utils.cache import TTLCache
        c = TTLCache(max_entries=500)
        errors = []

        def writer(prefix):
            try:
                for i in range(100):
                    c.set(f"{prefix}:{i}", i, ttl=10)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(f"t{t}",)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert c.stats["entries"] <= 500


# ── RequestID Middleware ─────────────────────────────────────────────


class TestRequestIDMiddleware:
    def test_response_has_request_id(self):
        resp = client.get("/api/health")
        assert "X-Request-ID" in resp.headers
        assert len(resp.headers["X-Request-ID"]) > 0

    def test_custom_request_id_preserved(self):
        resp = client.get("/api/health", headers={"X-Request-ID": "my-trace-123"})
        assert resp.headers["X-Request-ID"] == "my-trace-123"

    def test_response_has_timing_header(self):
        resp = client.get("/api/health")
        assert "X-Response-Time" in resp.headers


# ── Rate Limiter ─────────────────────────────────────────────────────


class TestRateLimiter:
    def test_rate_limiter_proxy_support(self):
        from sba.web.middleware import RateLimitMiddleware
        from unittest.mock import MagicMock
        rl = RateLimitMiddleware(app=MagicMock(), max_requests=10, window_seconds=60)
        mock_request = MagicMock()
        mock_request.headers = {"x-forwarded-for": "1.2.3.4, 10.0.0.1"}
        ip = rl._get_client_ip(mock_request)
        assert ip == "1.2.3.4"

    def test_rate_limiter_no_proxy(self):
        from sba.web.middleware import RateLimitMiddleware
        from unittest.mock import MagicMock
        rl = RateLimitMiddleware(app=MagicMock(), max_requests=10, window_seconds=60)
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client.host = "192.168.1.1"
        ip = rl._get_client_ip(mock_request)
        assert ip == "192.168.1.1"

    def test_rate_limiter_cleanup(self):
        from sba.web.middleware import RateLimitMiddleware
        from unittest.mock import MagicMock
        rl = RateLimitMiddleware(app=MagicMock(), max_requests=10, window_seconds=1)
        rl._cleanup_interval = 0  # Force cleanup to run
        rl._hits["old_ip"] = [time.monotonic() - 100]
        rl._cleanup_stale_entries(time.monotonic())
        assert "old_ip" not in rl._hits


# ── Settings Configuration ───────────────────────────────────────────


class TestSettingsConfig:
    def test_cors_origins_in_settings(self):
        from sba.config.settings import Settings
        s = Settings()
        assert "localhost" in s.CORS_ORIGINS

    def test_rate_limit_settings(self):
        from sba.config.settings import Settings
        s = Settings()
        assert s.RATE_LIMIT_MAX_REQUESTS > 0
        assert s.RATE_LIMIT_WINDOW_SECONDS > 0

    def test_version_bumped(self):
        assert app.version >= "2.4.0"


# ── Route Extraction Verification ───────────────────────────────────


class TestRouteExtraction:
    """Verify that extracted routes are properly registered."""

    def test_clv_routes_registered(self):
        paths = [r.path for r in app.routes]
        assert any("/clv/summary" in p for p in paths)
        assert any("/clv/record" in p for p in paths)

    def test_simulation_routes_registered(self):
        paths = [r.path for r in app.routes]
        assert any("/simulate" in p for p in paths)
        assert any("/backtest" in p for p in paths)

    def test_performance_routes_still_work(self):
        # Verify endpoints that stayed in performance.py still work
        resp = client.get("/api/cache/stats")
        assert resp.status_code == 200
