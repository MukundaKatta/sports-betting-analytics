"""Tests for new API endpoints: achievements, insights, bet rating, staking, performance."""

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


def _seed_data():
    """Seed database with test data."""
    from datetime import datetime

    from sba.data.db import get_connection, init_db
    from sba.data.db.repository import Repository
    from sba.models.domain import Event

    init_db()
    repo = Repository()
    with get_connection() as conn:
        repo.upsert_event(conn, Event(
            id="evt_1", sport="basketball_nba",
            home_team="Lakers", away_team="Celtics",
            commence_time=datetime(2025, 3, 15, 19, 0),
        ))
        bets = [
            ("evt_1", "h2h", "fanduel", -150, 100, "won", 66.67, "2025-03-10 14:00:00"),
            ("evt_1", "spreads", "draftkings", -110, 50, "lost", -50, "2025-03-11 18:00:00"),
            ("evt_1", "h2h", "fanduel", -130, 75, "won", 57.69, "2025-03-14 19:00:00"),
        ]
        for event_id, market, book, odds, stake, status, pl, placed in bets:
            conn.execute(
                """INSERT INTO bets (event_id, market, bookmaker, selection,
                   odds_american, recommended_stake, status, profit_loss, placed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, market, book, "Test", odds, stake, status, pl, placed),
            )


class TestAchievementsEndpoint:
    def test_returns_200(self, client):
        _seed_data()
        resp = client.get("/api/achievements")
        assert resp.status_code == 200

    def test_has_achievements_list(self, client):
        _seed_data()
        data = client.get("/api/achievements").json()
        assert "achievements" in data
        assert "summary" in data
        assert len(data["achievements"]) > 20

    def test_summary_has_rank(self, client):
        _seed_data()
        data = client.get("/api/achievements").json()
        assert "rank" in data["summary"]
        assert "total_points" in data["summary"]


class TestAchievementsSummary:
    def test_returns_200(self, client):
        _seed_data()
        resp = client.get("/api/achievements/summary")
        assert resp.status_code == 200

    def test_has_rank(self, client):
        _seed_data()
        data = client.get("/api/achievements/summary").json()
        assert "rank" in data
        assert "total_unlocked" in data


class TestInsightsEndpoint:
    def test_returns_200(self, client):
        _seed_data()
        resp = client.get("/api/insights")
        assert resp.status_code == 200

    def test_has_insights(self, client):
        _seed_data()
        data = client.get("/api/insights").json()
        assert "insights" in data
        assert "total" in data


class TestBetRating:
    def test_returns_200(self, client):
        resp = client.post("/api/bet-rating", json={"odds_american": -110, "ev_pct": 5.0})
        assert resp.status_code == 200

    def test_has_stars(self, client):
        data = client.post("/api/bet-rating", json={"odds_american": -110, "ev_pct": 10.0}).json()
        assert "stars" in data
        assert 1 <= data["stars"] <= 5
        assert "label" in data


class TestStakingCompare:
    def test_returns_200(self, client):
        resp = client.post("/api/staking/compare", json={
            "bankroll": 1000, "odds_decimal": 2.0, "win_probability": 0.55,
        })
        assert resp.status_code == 200

    def test_has_strategies(self, client):
        data = client.post("/api/staking/compare", json={
            "bankroll": 1000, "odds_decimal": 2.0, "win_probability": 0.55,
        }).json()
        assert "strategies" in data
        assert len(data["strategies"]) >= 5


class TestTodayPerformance:
    def test_returns_200(self, client):
        _seed_data()
        resp = client.get("/api/performance/today")
        assert resp.status_code == 200

    def test_has_fields(self, client):
        _seed_data()
        data = client.get("/api/performance/today").json()
        assert "profit" in data
        assert "wins" in data
        assert "win_rate" in data


class TestEquityCurve:
    def test_returns_200(self, client):
        _seed_data()
        resp = client.get("/api/performance/equity-curve")
        assert resp.status_code == 200

    def test_has_curve(self, client):
        _seed_data()
        data = client.get("/api/performance/equity-curve").json()
        assert "curve" in data
        assert "total_pnl" in data


class TestLineMovementTimeline:
    def test_returns_200(self, client):
        _seed_data()
        resp = client.get("/api/line-movement/timeline/evt_1")
        assert resp.status_code == 200

    def test_has_timeline(self, client):
        _seed_data()
        data = client.get("/api/line-movement/timeline/evt_1").json()
        assert "timeline" in data
        assert "bookmakers" in data
