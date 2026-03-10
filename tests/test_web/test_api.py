"""Tests for the web API endpoints."""

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


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
        # Create an event first (foreign key requirement)
        from sba.data.db import get_connection, init_db
        from sba.data.db.repository import Repository
        from sba.models.domain import Event
        from datetime import datetime

        init_db()
        repo = Repository()
        with get_connection() as conn:
            repo.upsert_event(conn, Event(
                id="test_event", sport="nba",
                home_team="A", away_team="B",
                commence_time=datetime(2025, 3, 15),
            ))

        resp = client.post("/api/bets/track", json={
            "event_id": "test_event",
            "market": "h2h",
            "selection": "Team A",
            "odds_american": 150,
            "stake": 25.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "tracked"
        assert "id" in data


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

    def test_player_page_loads(self, client):
        resp = client.get("/player/LeBron%20James")
        assert resp.status_code == 200

    def test_static_css_accessible(self, client):
        resp = client.get("/static/css/style.css")
        assert resp.status_code == 200

    def test_static_js_accessible(self, client):
        resp = client.get("/static/js/app.js")
        assert resp.status_code == 200
