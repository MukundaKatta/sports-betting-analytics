"""Tests for the analytics API endpoints."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


def _seed_bets():
    """Seed the database with test bets for analytics endpoints."""
    from sba.data.db import get_connection, init_db
    from sba.data.db.repository import Repository
    from sba.models.domain import Event

    init_db()
    repo = Repository()
    with get_connection() as conn:
        # Create events
        repo.upsert_event(conn, Event(
            id="evt_1", sport="basketball_nba",
            home_team="Lakers", away_team="Celtics",
            commence_time=datetime(2025, 3, 15, 19, 0),
        ))
        repo.upsert_event(conn, Event(
            id="evt_2", sport="americanfootball_nfl",
            home_team="Chiefs", away_team="Eagles",
            commence_time=datetime(2025, 3, 16, 13, 0),
        ))

        # Insert bets
        bets = [
            ("evt_1", "h2h", "fanduel", -150, 100, "won", 66.67, "2025-03-10 14:00:00"),
            ("evt_1", "spreads", "draftkings", -110, 50, "lost", -50, "2025-03-11 18:00:00"),
            ("evt_2", "h2h", "fanduel", 200, 50, "won", 100, "2025-03-12 20:00:00"),
            ("evt_2", "totals", "betmgm", -110, 100, "lost", -100, "2025-03-13 10:00:00"),
            ("evt_1", "h2h", "fanduel", -130, 75, "won", 57.69, "2025-03-14 19:00:00"),
        ]
        for event_id, market, book, odds, stake, status, pl, placed in bets:
            conn.execute(
                """INSERT INTO bets (event_id, market, bookmaker, selection,
                   odds_american, recommended_stake, status, profit_loss, placed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, market, book, "Test Selection", odds, stake, status, pl, placed),
            )


class TestAnalyticsBySport:
    def test_returns_200(self, client):
        _seed_bets()
        resp = client.get("/api/analytics/by-sport")
        assert resp.status_code == 200

    def test_returns_breakdown(self, client):
        _seed_bets()
        data = client.get("/api/analytics/by-sport").json()
        assert "breakdown" in data
        assert isinstance(data["breakdown"], list)


class TestAnalyticsByDay:
    def test_returns_200(self, client):
        _seed_bets()
        resp = client.get("/api/analytics/by-day")
        assert resp.status_code == 200

    def test_has_seven_days(self, client):
        _seed_bets()
        data = client.get("/api/analytics/by-day").json()
        assert len(data["breakdown"]) == 7


class TestAnalyticsByOddsRange:
    def test_returns_200(self, client):
        _seed_bets()
        resp = client.get("/api/analytics/by-odds-range")
        assert resp.status_code == 200


class TestAnalyticsByMarket:
    def test_returns_200(self, client):
        _seed_bets()
        resp = client.get("/api/analytics/by-market")
        assert resp.status_code == 200

    def test_has_breakdown(self, client):
        _seed_bets()
        data = client.get("/api/analytics/by-market").json()
        assert "breakdown" in data


class TestAnalyticsByBook:
    def test_returns_200(self, client):
        _seed_bets()
        resp = client.get("/api/analytics/by-book")
        assert resp.status_code == 200


class TestAnalyticsTrends:
    def test_returns_200(self, client):
        _seed_bets()
        resp = client.get("/api/analytics/trends")
        assert resp.status_code == 200

    def test_accepts_window_param(self, client):
        _seed_bets()
        resp = client.get("/api/analytics/trends?window=14")
        assert resp.status_code == 200

    def test_has_points(self, client):
        _seed_bets()
        data = client.get("/api/analytics/trends").json()
        assert "points" in data


class TestAnalyticsStreaks:
    def test_returns_200(self, client):
        _seed_bets()
        resp = client.get("/api/analytics/streaks")
        assert resp.status_code == 200

    def test_has_streak_fields(self, client):
        _seed_bets()
        data = client.get("/api/analytics/streaks").json()
        assert "current_type" in data
        assert "longest_win" in data
        assert "longest_loss" in data


class TestAnalyticsHeatmap:
    def test_returns_200(self, client):
        _seed_bets()
        resp = client.get("/api/analytics/heatmap")
        assert resp.status_code == 200

    def test_has_entries(self, client):
        _seed_bets()
        data = client.get("/api/analytics/heatmap").json()
        assert "heatmap" in data
