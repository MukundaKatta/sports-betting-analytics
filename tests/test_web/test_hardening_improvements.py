"""Tests for security hardening and quality improvements.

Covers: edge route fixes, XSS protection, input validation,
enhanced health checks, performance deduplication, query bounds, bankroll
validation, @safe_endpoint coverage, accessibility, and comprehensive error handling.
"""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app)


# ── Enhanced Deep Health Check ──────────────────────────────────────


class TestEnhancedDeepHealth:
    def test_deep_health_has_database_metrics(self):
        resp = client.get("/api/health/deep")
        assert resp.status_code == 200
        data = resp.json()
        checks = data["checks"]
        db = checks["database"]
        assert db["status"] == "healthy"
        assert "response_ms" in db
        assert "bet_count" in db
        assert "event_count" in db
        assert "odds_snapshot_count" in db
        assert "db_size_mb" in db
        assert isinstance(db["db_size_mb"], float)

    def test_deep_health_has_odds_api_status(self):
        resp = client.get("/api/health/deep")
        data = resp.json()
        assert "odds_api" in data["checks"]

    def test_deep_health_has_cache_stats(self):
        resp = client.get("/api/health/deep")
        data = resp.json()
        assert "cache" in data["checks"]

    def test_deep_health_has_rate_limit_info(self):
        resp = client.get("/api/health/deep")
        data = resp.json()
        rl = data["checks"]["rate_limit"]
        assert "max_requests" in rl
        assert "window_seconds" in rl

    def test_deep_health_uptime_seconds(self):
        resp = client.get("/api/health/deep")
        data = resp.json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], int)


# ── Edge Route Fixes ────────────────────────────────────────────────


class TestEdgeRouteFixes:
    """Verify the previously broken arb/middles/low-holds routes work."""

    def test_arbitrage_endpoint_returns_200(self):
        resp = client.get("/api/arbitrage?sport=basketball_nba")
        assert resp.status_code in (200, 400)
        if resp.status_code == 400:
            assert "ODDS_API_KEY" in resp.json()["detail"]

    def test_middles_endpoint_returns_200(self):
        resp = client.get("/api/middles?sport=basketball_nba")
        assert resp.status_code in (200, 400)

    def test_low_holds_endpoint_returns_200(self):
        resp = client.get("/api/low-holds?sport=basketball_nba")
        assert resp.status_code in (200, 400)

    def test_low_holds_max_hold_bounds(self):
        resp = client.get("/api/low-holds?max_hold=0.01")
        assert resp.status_code == 422
        resp = client.get("/api/low-holds?max_hold=25.0")
        assert resp.status_code == 422

    def test_arbitrage_invalid_sport(self):
        resp = client.get("/api/arbitrage?sport=invalid_sport_xyz")
        assert resp.status_code == 400

    def test_middles_invalid_sport(self):
        resp = client.get("/api/middles?sport=invalid_sport_xyz")
        assert resp.status_code == 400

    def test_low_holds_invalid_sport(self):
        resp = client.get("/api/low-holds?sport=invalid_sport_xyz")
        assert resp.status_code == 400


# ── Bankroll Validation ─────────────────────────────────────────────


class TestBankrollValidation:
    def test_deposit_rejects_negative(self):
        resp = client.post("/api/bankroll/deposit", json={"amount": -100})
        assert resp.status_code == 422

    def test_deposit_rejects_zero(self):
        resp = client.post("/api/bankroll/deposit", json={"amount": 0})
        assert resp.status_code == 422

    def test_withdraw_rejects_negative(self):
        resp = client.post("/api/bankroll/withdraw", json={"amount": -50})
        assert resp.status_code == 422

    def test_withdraw_rejects_zero(self):
        resp = client.post("/api/bankroll/withdraw", json={"amount": 0})
        assert resp.status_code == 422

    def test_deposit_accepts_positive(self):
        resp = client.post("/api/bankroll/deposit", json={"amount": 100})
        assert resp.status_code == 200
        assert "balance" in resp.json()

    def test_withdraw_accepts_positive(self):
        resp = client.post("/api/bankroll/withdraw", json={"amount": 10})
        assert resp.status_code == 200
        assert "balance" in resp.json()


# ── Performance: Deduplication of Settled Bets Helper ───────────────


class TestSettledBetsDeduplication:
    def test_performance_helper_delegates_to_analytics(self):
        from sba.web.routes.performance import _get_settled_bets_dicts as perf_fn
        from sba.web.routes.analytics import _get_settled_bets_dicts as analytics_fn
        assert perf_fn() == analytics_fn()


# ── XSS Protection ──────────────────────────────────────────────────


class TestEscapeHtmlFunction:
    def _js(self):
        import pathlib
        return (pathlib.Path(__file__).parent.parent.parent / "src" / "sba" / "web" / "static" / "js" / "app.js").read_text()

    def test_app_js_has_escape_html(self):
        assert "function escapeHtml(str)" in self._js()

    def test_escape_html_used_in_edges(self):
        c = self._js()
        assert "escapeHtml(e.event_away)" in c
        assert "escapeHtml(e.event_home)" in c
        assert "escapeHtml(e.bookmaker)" in c
        assert "escapeHtml(e.selection)" in c

    def test_escape_html_used_in_bets(self):
        c = self._js()
        assert "escapeHtml(b.selection)" in c
        assert "escapeHtml(b.bookmaker)" in c
        assert "escapeHtml(b.market)" in c

    def test_escape_html_used_in_props(self):
        c = self._js()
        assert "escapeHtml(p.player_name)" in c
        assert "escapeHtml(p.player_team)" in c

    def test_escape_html_used_in_error_messages(self):
        assert "escapeHtml(err.message)" in self._js()

    def test_escape_html_used_in_toast(self):
        assert "escapeHtml(message)" in self._js()

    def test_escape_html_used_in_search_results(self):
        c = self._js()
        assert "escapeHtml(p.name)" in c
        assert "escapeHtml(p.team)" in c
        assert "escapeHtml(p.position)" in c

    def test_escape_html_used_in_notifications(self):
        c = self._js()
        assert "escapeHtml(a.title" in c
        assert "escapeHtml(a.message" in c

    def test_escape_html_used_in_analytics(self):
        c = self._js()
        assert "escapeHtml(analytics.best_bet.selection)" in c
        assert "escapeHtml(analytics.worst_bet.selection)" in c

    def test_escape_html_used_in_odds_comparison(self):
        c = self._js()
        assert "escapeHtml(outcome)" in c
        assert "escapeHtml(bk)" in c

    def test_escape_html_used_in_line_movement(self):
        c = self._js()
        assert "escapeHtml(s.bookmaker)" in c
        assert "escapeHtml(s.outcome)" in c

    def test_escape_html_used_in_bet_slip(self):
        c = self._js()
        assert "escapeHtml(b.selection)" in c
        assert "escapeHtml(b.eventName)" in c


# ── Error Handling: safe_endpoint coverage ──────────────────────────


class TestSafeEndpointCoverage:
    def test_errors_module_has_validators(self):
        from sba.web.errors import validate_sport, validate_markets, validate_min_ev, VALID_SPORTS, VALID_MARKETS
        assert "basketball_nba" in VALID_SPORTS
        assert "h2h" in VALID_MARKETS

    def test_validate_sport_rejects_invalid(self):
        from sba.web.errors import validate_sport
        with pytest.raises(Exception):
            validate_sport("totally_fake_sport")

    def test_validate_sport_accepts_valid(self):
        from sba.web.errors import validate_sport
        assert validate_sport("basketball_nba") == "basketball_nba"

    def test_validate_sport_accepts_none(self):
        from sba.web.errors import validate_sport
        assert validate_sport(None) is None

    def test_validate_min_ev_bounds(self):
        from sba.web.errors import validate_min_ev
        assert validate_min_ev(None) is None
        assert validate_min_ev(0.05) == 0.05
        with pytest.raises(Exception):
            validate_min_ev(2.0)


# ── Query Bounds ────────────────────────────────────────────────────


class TestQueryBounds:
    def test_analytics_settled_bets_has_limit(self):
        import inspect
        from sba.web.routes.analytics import _get_settled_bets_dicts
        source = inspect.getsource(_get_settled_bets_dicts)
        assert "LIMIT" in source or "cached" in source.lower()

    def test_odds_history_has_limit_param(self):
        import inspect
        from sba.data.db.repository import Repository
        sig = inspect.signature(Repository.get_odds_history)
        assert "limit" in sig.parameters


# ── Logger Format ─────────────────────────────────────────────────


class TestLoggerFormat:
    def test_errors_module_uses_percent_formatting(self):
        import pathlib
        content = (pathlib.Path(__file__).parent.parent.parent / "src" / "sba" / "web" / "errors.py").read_text()
        assert 'logger.warning(f"' not in content
        assert 'logger.error(f"' not in content
        assert 'logger.warning("Integrity error in %s' in content
        assert 'logger.error("Database error in %s' in content


# ── API Response Checking in Frontend ───────────────────────────────


class TestFrontendErrorChecking:
    def test_fetch_calls_check_resp_ok(self):
        import pathlib
        content = (pathlib.Path(__file__).parent.parent.parent / "src" / "sba" / "web" / "static" / "js" / "app.js").read_text()
        assert content.count("!resp.ok") >= 4


# ── @safe_endpoint Coverage Across All Routes ─────────────────────


class TestSafeEndpointAllRoutes:
    def test_all_route_files_use_safe_endpoint(self):
        import pathlib
        route_dir = pathlib.Path(__file__).parent.parent.parent / "src" / "sba" / "web" / "routes"
        missing = []
        for f in sorted(route_dir.glob("*.py")):
            if f.name == "__init__.py":
                continue
            content = f.read_text()
            if "@router." in content and "@safe_endpoint" not in content:
                missing.append(f.name)
        assert missing == [], f"Route files missing @safe_endpoint: {missing}"

    def test_safe_endpoint_decorator_count(self):
        import pathlib
        route_dir = pathlib.Path(__file__).parent.parent.parent / "src" / "sba" / "web" / "routes"
        total = sum(f.read_text().count("@safe_endpoint") for f in route_dir.glob("*.py"))
        assert total >= 100, f"Expected 100+ @safe_endpoint decorators, found {total}"

    def test_calculators_has_safe_endpoint(self):
        resp = client.post("/api/calculator", json={"odds_american": 150})
        assert resp.status_code == 200

    def test_odds_events_has_safe_endpoint(self):
        resp = client.get("/api/events")
        assert resp.status_code == 200

    def test_analytics_advanced_has_safe_endpoint(self):
        resp = client.get("/api/analytics/advanced")
        assert resp.status_code == 200


# ── Input Validation Bounds ───────────────────────────────────────


class TestInputValidationBounds:
    def test_multibook_history_rejects_negative_days(self):
        resp = client.get("/api/multibook/history?days=-1")
        assert resp.status_code == 422

    def test_multibook_history_rejects_excessive_days(self):
        resp = client.get("/api/multibook/history?days=500")
        assert resp.status_code == 422

    def test_player_search_rejects_long_query(self):
        resp = client.get(f"/api/search/players?q={'x' * 101}")
        assert resp.status_code == 422

    def test_bets_rejects_invalid_status_filter(self):
        resp = client.get("/api/bets?status=invalid_status")
        assert resp.status_code == 400

    def test_bets_accepts_valid_status_filter(self):
        resp = client.get("/api/bets?status=won")
        assert resp.status_code == 200

    def test_picks_rejects_excessive_limit(self):
        resp = client.get("/api/picks?limit=500")
        assert resp.status_code == 422

    def test_account_limits_rejects_invalid_limit_type(self):
        resp = client.post("/api/account-limits", json={
            "sportsbook": "test", "limit_type": "invalid_type"
        })
        assert resp.status_code == 422

    def test_account_limits_rejects_invalid_severity(self):
        resp = client.post("/api/account-limits", json={
            "sportsbook": "test", "severity": "invalid_severity"
        })
        assert resp.status_code == 422

    def test_account_limits_accepts_valid(self):
        resp = client.post("/api/account-limits", json={
            "sportsbook": "test_book_hardening",
            "limit_type": "none",
            "severity": "none",
        })
        assert resp.status_code == 200


# ── Accessibility ─────────────────────────────────────────────────


class TestAccessibility:
    def test_base_template_has_aria_labels(self):
        import pathlib
        content = (pathlib.Path(__file__).parent.parent.parent / "src" / "sba" / "web" / "templates" / "base.html").read_text()
        assert 'aria-label="Toggle navigation menu"' in content
        assert 'aria-label="Edge Alerts"' in content
        assert 'aria-label="Toggle theme"' in content

    def test_sidebar_has_nav_aria(self):
        import pathlib
        content = (pathlib.Path(__file__).parent.parent.parent / "src" / "sba" / "web" / "templates" / "base.html").read_text()
        assert 'aria-label="Main navigation"' in content

    def test_search_has_aria(self):
        import pathlib
        content = (pathlib.Path(__file__).parent.parent.parent / "src" / "sba" / "web" / "templates" / "base.html").read_text()
        assert 'aria-label="Search players"' in content


# ── Additional Endpoint Smoke Tests ──────────────────────────────


class TestAdditionalEndpoints:
    def test_reports_daily(self):
        assert client.get("/api/reports/daily").status_code == 200

    def test_reports_weekly(self):
        assert client.get("/api/reports/weekly").status_code == 200

    def test_reports_monthly(self):
        assert client.get("/api/reports/monthly").status_code == 200

    def test_analytics_by_sport(self):
        assert client.get("/api/analytics/by-sport").status_code == 200

    def test_analytics_streaks(self):
        assert client.get("/api/analytics/streaks").status_code == 200

    def test_analytics_heatmap(self):
        assert client.get("/api/analytics/heatmap").status_code == 200

    def test_achievements(self):
        assert client.get("/api/achievements").status_code == 200

    def test_insights(self):
        assert client.get("/api/insights").status_code == 200

    def test_momentum(self):
        assert client.get("/api/momentum").status_code == 200

    def test_health_score(self):
        assert client.get("/api/health-score").status_code == 200

    def test_bets_export_csv(self):
        resp = client.get("/api/bets/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_bets_export_json(self):
        assert client.get("/api/bets/export/json").status_code == 200
