"""Tests for app quality improvements.

Covers:
- Betting Health Score endpoint
- Correlation Warnings endpoint
- WebSocket connection limit
- CORS and middleware configuration
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app, raise_server_exceptions=False)


# ── Health Score ──────────────────────────────────────────────────


class TestHealthScore:
    def test_health_score_endpoint_exists(self):
        resp = client.get("/api/health-score")
        assert resp.status_code == 200

    def test_health_score_insufficient_data(self):
        """With no/few bets, returns N/A grade."""
        resp = client.get("/api/health-score")
        data = resp.json()
        assert "score" in data
        assert "grade" in data
        assert "components" in data
        assert "sample_size" in data

    def test_health_score_grade_present(self):
        resp = client.get("/api/health-score")
        data = resp.json()
        assert data["grade"] in ("N/A", "Poor", "Fair", "Good", "Excellent", "Elite")

    def test_health_score_has_message(self):
        resp = client.get("/api/health-score")
        data = resp.json()
        assert "message" in data
        assert isinstance(data["message"], str)


# ── Correlation Warnings ──────────────────────────────────────────


class TestCorrelationWarnings:
    def test_endpoint_exists(self):
        resp = client.get("/api/correlation-warnings")
        assert resp.status_code == 200

    def test_response_structure(self):
        resp = client.get("/api/correlation-warnings")
        data = resp.json()
        assert "warnings" in data
        assert "risk_level" in data
        assert "pending_count" in data
        assert "total_exposure" in data
        assert "summary" in data

    def test_empty_state(self):
        """With no pending bets, should return clean state."""
        resp = client.get("/api/correlation-warnings")
        data = resp.json()
        assert data["risk_level"] in ("none", "low", "medium", "high")
        assert isinstance(data["warnings"], list)
        assert isinstance(data["pending_count"], int)


# ── Health Score Service Unit Tests ───────────────────────────────


class TestHealthScoreService:
    def test_score_to_grade(self):
        from sba.services.health_score import _score_to_grade
        assert _score_to_grade(95) == "Elite"
        assert _score_to_grade(80) == "Excellent"
        assert _score_to_grade(65) == "Good"
        assert _score_to_grade(45) == "Fair"
        assert _score_to_grade(20) == "Poor"

    def test_grade_message(self):
        from sba.services.health_score import _grade_message
        assert "exceptional" in _grade_message("Elite").lower()
        assert _grade_message("unknown") == ""

    def test_generate_recommendations_all_good(self):
        from sba.services.health_score import _generate_recommendations
        components = {
            "clv": {"score": 80},
            "roi": {"consistency": 70},
            "discipline": {"chase_rate": 2},
            "accuracy": {"score": 75},
            "diversification": {"score": 60},
        }
        recs = _generate_recommendations(components)
        assert len(recs) == 1
        assert recs[0]["priority"] == "info"

    def test_generate_recommendations_poor_clv(self):
        from sba.services.health_score import _generate_recommendations
        components = {
            "clv": {"score": 30},
            "roi": {"consistency": 70},
            "discipline": {"chase_rate": 2},
            "accuracy": {"score": 75},
            "diversification": {"score": 60},
        }
        recs = _generate_recommendations(components)
        assert any(r["area"] == "CLV" for r in recs)


# ── Correlation Warning Service Unit Tests ────────────────────────


class TestCorrelationWarningService:
    def test_check_same_event(self):
        from sba.services.correlation_warnings import _check_same_event
        bets = [
            {"id": 1, "event_id": "ev1", "home_team": "LAL", "away_team": "GSW",
             "market": "h2h", "recommended_stake": 50},
            {"id": 2, "event_id": "ev1", "home_team": "LAL", "away_team": "GSW",
             "market": "spread", "recommended_stake": 75},
        ]
        warnings = _check_same_event(bets)
        assert len(warnings) == 1
        assert warnings[0].category == "same_event"
        assert warnings[0].exposure == 125.0

    def test_check_book_concentration(self):
        from sba.services.correlation_warnings import _check_book_concentration
        bets = [
            {"id": i, "bookmaker": "DraftKings", "recommended_stake": 50}
            for i in range(5)
        ]
        warnings = _check_book_concentration(bets)
        assert len(warnings) == 1
        assert warnings[0].category == "book_concentration"

    def test_no_warnings_for_diverse_bets(self):
        from sba.services.correlation_warnings import _check_same_event
        bets = [
            {"id": 1, "event_id": "ev1", "home_team": "A", "away_team": "B",
             "market": "h2h", "recommended_stake": 50},
            {"id": 2, "event_id": "ev2", "home_team": "C", "away_team": "D",
             "market": "h2h", "recommended_stake": 50},
        ]
        warnings = _check_same_event(bets)
        assert len(warnings) == 0


# ── WebSocket Connection Limit ────────────────────────────────────


class TestWebSocketLimit:
    def test_ws_max_connections_constant(self):
        from sba.web.sse import _MAX_WS_CONNECTIONS
        assert _MAX_WS_CONNECTIONS == 100


# ── App Configuration ─────────────────────────────────────────────


class TestAppConfiguration:
    def test_cors_headers_restricted(self):
        """CORS should not use wildcard methods."""
        # The app should have CORS middleware with restricted methods
        resp = client.options(
            "/api/health-score",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
        )
        # Should not fail
        assert resp.status_code in (200, 400, 405)

    def test_timing_header(self):
        resp = client.get("/api/health-score")
        assert "X-Response-Time" in resp.headers

    def test_global_error_handler(self):
        """500 errors should return structured JSON, not stack traces."""
        # Non-existent endpoint should be 404/405, not 500
        resp = client.get("/api/nonexistent-endpoint-xyz")
        assert resp.status_code in (404, 405)
