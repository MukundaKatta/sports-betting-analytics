"""Tests for v2.5 improvements.

Covers:
- SQL-based /bets pagination (LIMIT/OFFSET instead of Python slicing)
- Single-query /odds-screen (N+1 → JOIN)
- Cached analytics helper (_get_settled_bets_dicts)
- New database indexes
- prefers-reduced-motion CSS
- Version bump
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app, raise_server_exceptions=False)


# ── SQL Pagination ───────────────────────────────────────────────────


class TestBetsPagination:
    def test_bets_default(self):
        resp = client.get("/api/bets")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_bets" in data
        assert "wins" in data
        assert "losses" in data
        assert "pushes" in data
        assert "pending" in data
        assert "bets" in data
        assert "roi" in data

    def test_bets_pagination_params(self):
        resp = client.get("/api/bets?page=1&per_page=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["bets"]) <= 5

    def test_bets_page_2(self):
        resp = client.get("/api/bets?page=2&per_page=5")
        assert resp.status_code == 200

    def test_bets_status_filter(self):
        resp = client.get("/api/bets?status=pending")
        assert resp.status_code == 200

    def test_bets_invalid_page(self):
        resp = client.get("/api/bets?page=0")
        assert resp.status_code == 422

    def test_bets_per_page_limit(self):
        resp = client.get("/api/bets?per_page=501")
        assert resp.status_code == 422


# ── Odds Screen Single Query ────────────────────────────────────────


class TestOddsScreen:
    def test_odds_screen_default(self):
        resp = client.get("/api/odds-screen")
        assert resp.status_code == 200
        data = resp.json()
        assert "sport" in data
        assert "market" in data
        assert "events" in data
        assert "total_events" in data

    def test_odds_screen_custom_sport(self):
        resp = client.get("/api/odds-screen?sport=americanfootball_nfl&market=spreads")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sport"] == "americanfootball_nfl"
        assert data["market"] == "spreads"

    def test_odds_screen_event_structure(self):
        resp = client.get("/api/odds-screen")
        assert resp.status_code == 200
        data = resp.json()
        for event in data["events"]:
            assert "event_id" in event
            assert "home_team" in event
            assert "away_team" in event
            assert "outcomes" in event
            assert "best_odds" in event
            assert "num_books" in event


# ── Analytics Caching ────────────────────────────────────────────────


class TestAnalyticsCaching:
    def test_settled_bets_cached(self):
        """Calling _get_settled_bets_dicts twice should use cache on second call."""
        from sba.utils.cache import cache
        from sba.web.routes.analytics import _get_settled_bets_dicts

        # Clear any existing cache
        cache.invalidate("settled_bets:")

        # First call populates cache
        result1 = _get_settled_bets_dicts()

        # Verify it's in cache now
        cached = cache.get("settled_bets:all")
        assert cached is not None
        assert cached == result1

        # Second call should return same data from cache
        result2 = _get_settled_bets_dicts()
        assert result2 == result1

    def test_analytics_by_sport(self):
        resp = client.get("/api/analytics/by-sport")
        assert resp.status_code == 200
        data = resp.json()
        assert "breakdown" in data
        assert "total_bets" in data

    def test_analytics_by_day(self):
        resp = client.get("/api/analytics/by-day")
        assert resp.status_code == 200

    def test_analytics_by_odds_range(self):
        resp = client.get("/api/analytics/by-odds-range")
        assert resp.status_code == 200

    def test_analytics_by_market(self):
        resp = client.get("/api/analytics/by-market")
        assert resp.status_code == 200

    def test_analytics_by_book(self):
        resp = client.get("/api/analytics/by-book")
        assert resp.status_code == 200

    def test_analytics_heatmap(self):
        resp = client.get("/api/analytics/heatmap")
        assert resp.status_code == 200
        data = resp.json()
        assert "heatmap" in data

    def test_analytics_streaks(self):
        resp = client.get("/api/analytics/streaks")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_type" in data
        assert "longest_win" in data

    def test_analytics_trends(self):
        resp = client.get("/api/analytics/trends?window=7")
        assert resp.status_code == 200
        data = resp.json()
        assert data["window"] == 7


# ── Database Indexes ─────────────────────────────────────────────────


class TestDatabaseIndexes:
    def test_new_indexes_in_schema(self):
        from sba.data.db.schema import SCHEMA_SQL
        assert "idx_odds_event_market_book" in SCHEMA_SQL
        assert "idx_bets_event" in SCHEMA_SQL

    def test_indexes_created_after_init(self):
        from sba.data.db import get_connection, init_db
        init_db()  # Re-run to pick up new indexes
        with get_connection() as conn:
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        index_names = {r["name"] for r in indexes}
        assert "idx_odds_event_market_book" in index_names
        assert "idx_bets_event" in index_names


# ── CSS Accessibility ────────────────────────────────────────────────


class TestCSSAccessibility:
    def test_reduced_motion_in_css(self):
        css_path = "/Users/ubl/sports-betting-analytics/src/sba/web/static/css/style.css"
        with open(css_path) as f:
            css = f.read()
        assert "prefers-reduced-motion" in css
        assert "animation-duration: 0.01ms" in css
        assert "transition-duration: 0.01ms" in css


# ── Version ──────────────────────────────────────────────────────────


class TestVersion:
    def test_version_bumped(self):
        assert app.version >= "2.5.0"
