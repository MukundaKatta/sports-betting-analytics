"""Tests for the web API endpoints."""

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


def _create_test_event(event_id="test_event"):
    """Helper to create a test event for foreign key requirements."""
    from datetime import datetime

    from sba.data.db import get_connection, init_db
    from sba.data.db.repository import Repository
    from sba.models.domain import Event

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
        assert data["version"] == "2.0.0"
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

    def test_line_movement_page_loads(self, client):
        resp = client.get("/line-movement")
        assert resp.status_code == 200
        assert "Line Movement" in resp.text

    def test_api_docs_accessible(self, client):
        resp = client.get("/api/docs")
        assert resp.status_code == 200


class TestCSVExport:
    def test_export_returns_csv(self, client):
        resp = client.get("/api/bets/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "sba_bets_export.csv" in resp.headers.get("content-disposition", "")
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 1  # at least header row
        assert "ID" in lines[0]
        assert "Market" in lines[0]

    def test_export_with_bet_data(self, client):
        _create_test_event("test_event_csv")
        client.post("/api/bets/track", json={
            "event_id": "test_event_csv",
            "market": "h2h",
            "selection": "Team A",
            "odds_american": 150,
            "stake": 25.0,
        })
        resp = client.get("/api/bets/export")
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 2  # header + at least one data row


class TestSearchPlayers:
    def test_search_returns_list(self, client):
        resp = client.get("/api/search/players?q=test")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_search_requires_min_length(self, client):
        resp = client.get("/api/search/players?q=a")
        assert resp.status_code == 422


class TestUpdateSettings:
    def test_update_bankroll(self, client):
        resp = client.put("/api/settings", json={"bankroll": 5000.0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"]["bankroll"] == 5000.0

    def test_update_multiple_fields(self, client):
        resp = client.put("/api/settings", json={
            "kelly_fraction": 0.3,
            "ev_threshold": 4.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "kelly_fraction" in data["updated"]
        assert "ev_threshold" in data["updated"]

    def test_update_empty_body(self, client):
        resp = client.put("/api/settings", json={})
        assert resp.status_code == 200
        assert resp.json()["updated"] == {}


class TestAlertsEndpoint:
    def test_get_alerts(self, client):
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "count" in data
        assert isinstance(data["alerts"], list)

    def test_clear_alerts(self, client):
        resp = client.delete("/api/alerts")
        assert resp.status_code == 200
        assert resp.json()["cleared"] is True


class TestOddsComparisonEndpoint:
    def test_odds_comparison_no_data(self, client):
        _create_test_event("test_odds_cmp")
        resp = client.get("/api/odds-comparison/test_odds_cmp")
        assert resp.status_code == 200
        data = resp.json()
        assert "bookmakers" in data
        assert "outcomes" in data
        assert "total_snapshots" in data

    def test_odds_comparison_with_market(self, client):
        _create_test_event("test_odds_cmp2")
        resp = client.get("/api/odds-comparison/test_odds_cmp2?market=spreads")
        assert resp.status_code == 200
        assert isinstance(resp.json()["bookmakers"], list)


class TestOddsComparisonPage:
    def test_odds_comparison_page_loads(self, client):
        resp = client.get("/odds-comparison")
        assert resp.status_code == 200
        assert "Odds Comparison" in resp.text


class TestSimulatorEndpoint:
    def test_simulate_default(self, client):
        resp = client.post("/api/simulate", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "percentiles" in data
        assert "summary" in data
        assert "p50" in data["percentiles"]
        assert data["summary"]["profitable_pct"] >= 0

    def test_simulate_custom(self, client):
        resp = client.post("/api/simulate", json={
            "bankroll": 5000,
            "num_bets": 50,
            "avg_odds": 150,
            "win_rate": 0.45,
            "kelly_fraction": 0.1,
            "simulations": 10,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulations"] == 10
        assert data["num_bets"] == 50
        assert len(data["percentiles"]["p50"]) == 51  # 0 to 50


class TestLiveOddsEndpoint:
    def test_live_odds_returns_list(self, client):
        resp = client.get("/api/live-odds")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_live_odds_with_limit(self, client):
        resp = client.get("/api/live-odds?limit=5")
        assert resp.status_code == 200


class TestAdvancedAnalytics:
    def test_advanced_analytics_returns_metrics(self, client):
        resp = client.get("/api/analytics/advanced")
        assert resp.status_code == 200
        data = resp.json()
        assert "sharpe_ratio" in data
        assert "max_drawdown" in data
        assert "profit_factor" in data
        assert "longest_win_streak" in data
        assert "cumulative_pnl" in data
        assert isinstance(data["cumulative_pnl"], list)


class TestWatchlistEndpoint:
    def test_get_watchlist(self, client):
        resp = client.get("/api/watchlist")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "count" in data

    def test_add_and_remove_watchlist(self, client):
        # Add
        resp = client.post("/api/watchlist?event_id=test123&label=Test+Game")
        assert resp.status_code == 200
        assert resp.json()["status"] == "added"

        # Duplicate
        resp = client.post("/api/watchlist?event_id=test123&label=Test+Game")
        assert resp.json()["status"] == "already_exists"

        # Remove
        resp = client.delete("/api/watchlist/test123")
        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"


class TestCalculatorEndpoint:
    def test_calculator_default(self, client):
        resp = client.post("/api/calculator", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "odds_american" in data
        assert "odds_decimal" in data
        assert "odds_fractional" in data
        assert "implied_probability" in data
        assert "payout" in data

    def test_calculator_with_probability(self, client):
        resp = client.post("/api/calculator", json={
            "odds_american": -110,
            "stake": 100,
            "win_probability": 0.55,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ev_pct"] is not None
        assert data["kelly_pct"] is not None

    def test_calculator_positive_odds(self, client):
        resp = client.post("/api/calculator", json={
            "odds_american": 200,
            "stake": 50,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["payout"] == 100.0
        assert data["total_return"] == 150.0


class TestHedgeCalculator:
    def test_hedge_calc(self, client):
        resp = client.post("/api/calculator/hedge", json={
            "original_odds": 200,
            "original_stake": 100,
            "hedge_odds": -150,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "hedge_stake" in data
        assert "total_invested" in data
        assert "guaranteed_profit" in data


class TestBetsExportJson:
    def test_export_json_returns_list(self, client):
        resp = client.get("/api/bets/export/json")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestNewPages:
    def test_simulator_page_loads(self, client):
        resp = client.get("/simulator")
        assert resp.status_code == 200
        assert "Simulator" in resp.text

    def test_live_feed_page_loads(self, client):
        resp = client.get("/live-feed")
        assert resp.status_code == 200
        assert "Live" in resp.text

    def test_calculator_page_loads(self, client):
        resp = client.get("/calculator")
        assert resp.status_code == 200
        assert "Calculator" in resp.text
