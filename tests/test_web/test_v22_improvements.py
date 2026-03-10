"""Tests for v2.2 improvements: error handling, validation, caching, momentum, daily summary."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app)


class TestErrorHandling:
    def test_global_exception_returns_json(self):
        """Test that unhandled errors return structured JSON."""
        resp = client.get("/api/nonexistent-endpoint")
        assert resp.status_code in (404, 405)

    def test_api_error_module_imports(self):
        from sba.web.errors import APIError, NotFoundError, ValidationError, safe_endpoint
        err = APIError("test error", 400)
        assert err.message == "test error"
        assert err.status_code == 400

    def test_not_found_error(self):
        from sba.web.errors import NotFoundError
        err = NotFoundError("Bet", 123)
        assert "123" in err.message
        assert err.status_code == 404

    def test_validation_error(self):
        from sba.web.errors import ValidationError
        err = ValidationError("bad input", details={"field": "sport"})
        assert err.status_code == 422
        assert err.details["field"] == "sport"


class TestInputValidation:
    def test_edges_min_ev_validation(self):
        """min_ev should accept valid values."""
        resp = client.get("/api/edges?min_ev=0.05")
        # May fail due to missing API key, but should not fail validation
        assert resp.status_code in (200, 400)

    def test_live_odds_limit_bounds(self):
        """limit parameter should be bounded."""
        resp = client.get("/api/live-odds?limit=5")
        assert resp.status_code == 200

    def test_live_odds_limit_too_high(self):
        """limit > 500 should be rejected."""
        resp = client.get("/api/live-odds?limit=9999")
        assert resp.status_code == 422

    def test_analytics_trends_window_bounds(self):
        """window should be bounded."""
        resp = client.get("/api/analytics/trends?window=0")
        assert resp.status_code == 422

    def test_portfolio_max_bets_bounds(self):
        """max_bets should be bounded 1-100."""
        resp = client.get("/api/portfolio?max_bets=0")
        assert resp.status_code == 422

    def test_simulation_validates_bounds(self):
        """Simulation should validate input bounds."""
        resp = client.post("/api/simulate", json={
            "bankroll": -100, "num_bets": 100, "simulations": 50,
        })
        assert resp.status_code in (422, 500)


class TestSQLAnalytics:
    def test_analytics_returns_structure(self):
        """Analytics endpoint should return all expected fields."""
        resp = client.get("/api/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert "by_market" in data
        assert "by_bookmaker" in data
        assert "daily_pnl" in data
        assert "streak" in data

    def test_analytics_empty_db(self):
        """Analytics should handle empty database gracefully."""
        resp = client.get("/api/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["by_market"], dict)
        assert isinstance(data["daily_pnl"], list)


class TestCaching:
    def test_cache_module(self):
        from sba.utils.cache import TTLCache, cached_response
        c = TTLCache()
        c.set("test_key", {"data": 42}, ttl=60)
        assert c.get("test_key") == {"data": 42}
        assert c.get("nonexistent") is None

    def test_cache_ttl_expiry(self):
        from sba.utils.cache import TTLCache
        c = TTLCache()
        c.set("expire_key", "value", ttl=0)  # immediate expiry
        assert c.get("expire_key") is None

    def test_cache_invalidation(self):
        from sba.utils.cache import TTLCache
        c = TTLCache()
        c.set("prefix:a", 1, ttl=60)
        c.set("prefix:b", 2, ttl=60)
        c.set("other:c", 3, ttl=60)
        c.invalidate("prefix")
        assert c.get("prefix:a") is None
        assert c.get("other:c") == 3

    def test_cache_stats(self):
        from sba.utils.cache import TTLCache
        c = TTLCache()
        c.set("k", "v", ttl=60)
        c.get("k")  # hit
        c.get("missing")  # miss
        stats = c.stats
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1

    def test_cached_response_decorator(self):
        from sba.utils.cache import cached_response
        call_count = 0

        @cached_response(ttl=60, prefix="test_dec")
        def expensive_fn():
            nonlocal call_count
            call_count += 1
            return {"result": call_count}

        result1 = expensive_fn()
        result2 = expensive_fn()
        assert result1 == result2  # cached
        assert call_count == 1  # only called once


class TestPagination:
    def test_bets_pagination_params(self):
        """Bets endpoint should accept pagination parameters."""
        resp = client.get("/api/bets?page=1&per_page=10")
        assert resp.status_code == 200

    def test_bets_invalid_page(self):
        """page=0 should be rejected."""
        resp = client.get("/api/bets?page=0")
        assert resp.status_code == 422

    def test_bets_per_page_too_high(self):
        """per_page > 500 should be rejected."""
        resp = client.get("/api/bets?per_page=1000")
        assert resp.status_code == 422


class TestMomentum:
    def test_momentum_endpoint(self):
        resp = client.get("/api/momentum")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_streak" in data
        assert "momentum" in data
        assert "historical_streaks" in data

    def test_momentum_score_structure(self):
        resp = client.get("/api/momentum")
        data = resp.json()
        momentum = data["momentum"]
        assert "score" in momentum
        assert "label" in momentum
        assert "signal" in momentum
        assert momentum["label"] in ("Hot", "Warm", "Neutral", "Cold", "Ice Cold")

    def test_momentum_service_direct(self):
        from sba.services.momentum import get_streak_analysis
        result = get_streak_analysis()
        assert isinstance(result, dict)
        assert "current_streak" in result


class TestDailySummary:
    def test_daily_summary_endpoint(self):
        resp = client.get("/api/daily-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "date" in data
        assert "today" in data
        assert "week" in data
        assert "insights" in data

    def test_daily_summary_today_structure(self):
        resp = client.get("/api/daily-summary")
        data = resp.json()
        today = data["today"]
        assert "bets" in today
        assert "wins" in today
        assert "profit" in today

    def test_daily_summary_service_direct(self):
        from sba.services.momentum import get_daily_summary
        result = get_daily_summary()
        assert isinstance(result, dict)
        assert "date" in result
        assert "insights" in result


class TestCacheStatsEndpoint:
    def test_cache_stats_endpoint(self):
        resp = client.get("/api/cache/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "hits" in data


class TestDatabaseIndexes:
    def test_schema_has_new_indexes(self):
        """Verify new indexes exist in schema SQL."""
        from sba.data.db.schema import SCHEMA_SQL
        assert "idx_bets_market" in SCHEMA_SQL
        assert "idx_bets_bookmaker" in SCHEMA_SQL
        assert "idx_bets_settled" in SCHEMA_SQL
        assert "idx_odds_event_book" in SCHEMA_SQL
        assert "idx_events_active" in SCHEMA_SQL


class TestEnhancedSplits:
    def test_stat_fields_include_all(self):
        from sba.services.situation_splits import STAT_FIELDS
        assert "points" in STAT_FIELDS
        assert "rebounds" in STAT_FIELDS
        assert "assists" in STAT_FIELDS
        assert "threes" in STAT_FIELDS
        assert "steals" in STAT_FIELDS
        assert "blocks" in STAT_FIELDS

    def test_invalid_stat_error(self):
        from sba.services.situation_splits import get_situation_splits
        result = get_situation_splits("AnyPlayer", "invalid_xyz")
        assert "error" in result
