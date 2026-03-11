"""Tests for v3.1 improvements.

Covers:
- Dashboard Summary API (aggregated endpoint)
- Performance Digest service (weekly/monthly)
- Enhanced dashboard widgets (health score, digest)
- New view pages
- Version alignment (3.1.0)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app, raise_server_exceptions=False)


# ── Dashboard Summary API ──────────────────────────────────────


class TestDashboardSummary:
    def test_dashboard_summary_endpoint(self):
        """GET /api/dashboard/summary should return 200."""
        resp = client.get("/api/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "today" in data
        assert "lifetime" in data
        assert "bankroll" in data
        assert "health_score" in data
        assert "streaks" in data
        assert "top_insights" in data
        assert "data_status" in data

    def test_dashboard_summary_today_structure(self):
        """Today's section should have required fields."""
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        today = data["today"]
        assert "profit" in today
        assert "bets" in today
        assert "wins" in today
        assert "pending" in today
        assert "roi_pct" in today

    def test_dashboard_summary_lifetime_structure(self):
        """Lifetime section should have required fields."""
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        lifetime = data["lifetime"]
        assert "total_bets" in lifetime
        assert "wins" in lifetime
        assert "profit" in lifetime
        assert "roi_pct" in lifetime
        assert "win_rate" in lifetime

    def test_dashboard_summary_health_score(self):
        """Health score should have score and grade."""
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        hs = data["health_score"]
        assert "score" in hs
        assert "grade" in hs

    def test_dashboard_summary_insights_limited(self):
        """Top insights should be limited to 3."""
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert len(data["top_insights"]) <= 3


# ── Performance Digest Service ─────────────────────────────────


class TestPerformanceDigestService:
    def test_generate_weekly_digest(self):
        """Should generate a weekly digest."""
        from sba.services.performance_digest import generate_digest
        digest = generate_digest("weekly")
        assert digest.period == "weekly"
        assert digest.current is not None
        assert digest.grade in ("A+", "A", "B+", "B", "C+", "C", "D", "F")
        assert digest.grade_trend in ("improving", "declining", "stable")

    def test_generate_monthly_digest(self):
        """Should generate a monthly digest."""
        from sba.services.performance_digest import generate_digest
        digest = generate_digest("monthly")
        assert digest.period == "monthly"
        assert digest.current is not None

    def test_digest_current_period_fields(self):
        """Current period should have all required fields."""
        from sba.services.performance_digest import generate_digest
        digest = generate_digest("weekly")
        p = digest.current
        assert hasattr(p, "total_bets")
        assert hasattr(p, "wins")
        assert hasattr(p, "losses")
        assert hasattr(p, "profit")
        assert hasattr(p, "roi_pct")
        assert hasattr(p, "win_rate")
        assert hasattr(p, "avg_odds")

    def test_digest_highlights_and_warnings(self):
        """Digest should have highlights and warnings lists."""
        from sba.services.performance_digest import generate_digest
        digest = generate_digest("weekly")
        assert isinstance(digest.highlights, list)
        assert isinstance(digest.warnings, list)

    def test_digest_breakdowns(self):
        """Should have by_sport, by_market, by_book breakdowns."""
        from sba.services.performance_digest import generate_digest
        digest = generate_digest("weekly")
        assert isinstance(digest.by_sport, list)
        assert isinstance(digest.by_market, list)
        assert isinstance(digest.by_book, list)

    def test_digest_streaks(self):
        """Should have streak info."""
        from sba.services.performance_digest import generate_digest
        digest = generate_digest("weekly")
        assert "current" in digest.streaks
        assert "current_type" in digest.streaks
        assert "longest_win" in digest.streaks
        assert "longest_loss" in digest.streaks


# ── Performance Digest API ─────────────────────────────────────


class TestPerformanceDigestAPI:
    def test_weekly_digest_endpoint(self):
        """GET /api/performance/digest?period=weekly should return 200."""
        resp = client.get("/api/performance/digest", params={"period": "weekly"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "weekly"
        assert "grade" in data
        assert "current" in data
        assert "trends" in data
        assert "highlights" in data
        assert "warnings" in data

    def test_monthly_digest_endpoint(self):
        """GET /api/performance/digest?period=monthly should return 200."""
        resp = client.get("/api/performance/digest", params={"period": "monthly"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "monthly"

    def test_default_period_is_weekly(self):
        """Default period should be weekly."""
        resp = client.get("/api/performance/digest")
        assert resp.status_code == 200
        assert resp.json()["period"] == "weekly"

    def test_digest_response_structure(self):
        """Full response should have all required fields."""
        resp = client.get("/api/performance/digest")
        data = resp.json()
        required = ["period", "grade", "grade_trend", "current",
                     "trends", "streaks", "by_sport", "by_market",
                     "by_book", "highlights", "warnings"]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_digest_current_structure(self):
        """Current period should have complete structure."""
        resp = client.get("/api/performance/digest")
        data = resp.json()
        current = data["current"]
        assert "total_bets" in current
        assert "wins" in current
        assert "losses" in current
        assert "profit" in current
        assert "roi_pct" in current
        assert "win_rate" in current


# ── New View Pages ──────────────────────────────────────────────


class TestNewViewPages:
    def test_performance_digest_page(self):
        """Performance digest page should load."""
        resp = client.get("/performance-digest")
        assert resp.status_code == 200
        assert "Performance Digest" in resp.text

    def test_dashboard_loads(self):
        """Dashboard should still load correctly."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text

    def test_dashboard_has_health_score_widget(self):
        """Dashboard should have health score widget."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "dash-health-score" in resp.text

    def test_dashboard_has_digest_widget(self):
        """Dashboard should have weekly digest widget."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "dash-digest" in resp.text


# ── Version Alignment ──────────────────────────────────────────


class TestVersionAlignment:
    def test_version_is_3_1_plus(self):
        """__version__ should be at least 3.1.0."""
        from sba import __version__
        assert __version__ >= "3.1.0"

    def test_app_version_matches(self):
        """FastAPI app.version should match __version__."""
        from sba import __version__
        assert app.version == __version__

    def test_health_version(self):
        """Health endpoint should report current version."""
        from sba import __version__
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["version"] == __version__


# ── Health Score Integration ───────────────────────────────────


class TestHealthScoreIntegration:
    def test_health_score_endpoint(self):
        """GET /api/health-score should return 200."""
        resp = client.get("/api/health-score")
        assert resp.status_code == 200
        data = resp.json()
        # Either we have a score or a message saying we need more data
        assert "score" in data or "message" in data

    def test_health_score_from_dashboard_summary(self):
        """Dashboard summary should include health score."""
        resp = client.get("/api/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "health_score" in data
        assert "score" in data["health_score"]
        assert "grade" in data["health_score"]
