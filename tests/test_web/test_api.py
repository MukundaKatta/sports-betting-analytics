"""Tests for the web API endpoints."""

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


def _create_test_event(event_id="test_event"):
    """Helper to create a test event for foreign key requirements."""
    from sba.data.db import get_connection, init_db
    from sba.data.db.repository import Repository
    from sba.models.domain import Event
    from datetime import datetime

    init_db()
    repo = Repository()
    with get_connection() as conn:
        repo.upsert_event(conn, Event(
            id=event_id, sport="nba",
            home_team="Team A", away_team="Team B",
            commence_time=datetime(2025, 3, 15),
        ))


class TestStatusEndpoint:
    def test_status_returns_counts(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "players" in data
        assert "bets" in data

    def test_status_values_non_negative(self, client):
        data = client.get("/api/status").json()
        assert data["events"] >= 0
        assert data["odds_snapshots"] >= 0
        assert data["players"] >= 0


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.2.0"
        assert data["database"] == "healthy"
        assert "uptime" in data

    def test_health_has_timing_header(self, client):
        resp = client.get("/api/health")
        assert "x-response-time" in resp.headers


class TestBetsEndpoint:
    def test_bets_returns_summary(self, client):
        resp = client.get("/api/bets")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_bets" in data
        assert "wins" in data
        assert "roi" in data
        assert "bets" in data
        assert isinstance(data["bets"], list)

    def test_track_bet(self, client):
        _create_test_event("test_event_track")

        resp = client.post("/api/bets/track", json={
            "event_id": "test_event_track",
            "market": "h2h",
            "selection": "Team A",
            "odds_american": 150,
            "stake": 25.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "tracked"
        assert "id" in data

    def test_settle_bet(self, client):
        _create_test_event("test_event_settle")

        # Track a bet first
        track_resp = client.post("/api/bets/track", json={
            "event_id": "test_event_settle",
            "market": "h2h",
            "selection": "Team A",
            "odds_american": -110,
            "stake": 50.0,
        })
        bet_id = track_resp.json()["id"]

        # Settle it
        resp = client.put(f"/api/bets/{bet_id}/settle", json={
            "status": "won",
            "profit_loss": 45.45,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "won"
        assert data["profit_loss"] == 45.45

    def test_settle_bet_invalid_status(self, client):
        resp = client.put("/api/bets/1/settle", json={
            "status": "invalid",
            "profit_loss": 0,
        })
        assert resp.status_code == 400

    def test_delete_bet(self, client):
        _create_test_event("test_event_delete")

        track_resp = client.post("/api/bets/track", json={
            "event_id": "test_event_delete",
            "market": "h2h",
            "selection": "Team B",
            "odds_american": 200,
            "stake": 10.0,
        })
        bet_id = track_resp.json()["id"]

        resp = client.delete(f"/api/bets/{bet_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


class TestAnalyticsEndpoint:
    def test_analytics_returns_breakdown(self, client):
        resp = client.get("/api/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert "by_market" in data
        assert "by_bookmaker" in data
        assert "daily_pnl" in data
        assert "streak" in data
        assert isinstance(data["by_market"], dict)
        assert isinstance(data["daily_pnl"], list)

    def test_analytics_streak_structure(self, client):
        data = client.get("/api/analytics").json()
        assert "type" in data["streak"]
        assert "count" in data["streak"]


class TestSettingsEndpoint:
    def test_settings_returns_config(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "bankroll" in data
        assert "kelly_fraction" in data
        assert "ev_threshold" in data
        assert "default_sport" in data
        assert data["bankroll"] > 0
        assert 0 < data["kelly_fraction"] <= 1


class TestEventsEndpoint:
    def test_events_returns_list(self, client):
        resp = client.get("/api/events")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestViewRoutes:
    def test_dashboard_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "SBA" in resp.text

    def test_edges_page_loads(self, client):
        resp = client.get("/edges")
        assert resp.status_code == 200
        assert "Edge Finder" in resp.text

    def test_props_page_loads(self, client):
        resp = client.get("/props")
        assert resp.status_code == 200
        assert "Player Props" in resp.text

    def test_bets_page_loads(self, client):
        resp = client.get("/my-bets")
        assert resp.status_code == 200
        assert "My Bets" in resp.text

    def test_analytics_page_loads(self, client):
        resp = client.get("/analytics")
        assert resp.status_code == 200
        assert "Analytics" in resp.text

    def test_settings_page_loads(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "Settings" in resp.text

    def test_player_page_loads(self, client):
        resp = client.get("/player/LeBron%20James")
        assert resp.status_code == 200

    def test_static_css_accessible(self, client):
        resp = client.get("/static/css/style.css")
        assert resp.status_code == 200

    def test_static_js_accessible(self, client):
        resp = client.get("/static/js/app.js")
        assert resp.status_code == 200

    def test_api_docs_accessible(self, client):
        resp = client.get("/api/docs")
        assert resp.status_code == 200
