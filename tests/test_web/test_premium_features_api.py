"""Tests for premium feature API endpoints: devig, bet grades, backtest, public money."""

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestDevigAPI:
    def test_quick_devig(self, client):
        resp = client.post("/api/calculator/devig", json={
            "odds_american": [-110, -110],
            "method": "multiplicative",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == "multiplicative"
        assert len(data["outcomes"]) == 2
        assert data["vig_removed"] > 0

    def test_devig_with_names(self, client):
        resp = client.post("/api/calculator/devig", json={
            "odds_american": [-150, 130],
            "outcome_names": ["Lakers", "Celtics"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["outcomes"][0]["name"] == "Lakers"

    def test_devig_all_methods(self, client):
        for method in ["multiplicative", "additive", "power", "worst_case"]:
            resp = client.post("/api/calculator/devig", json={
                "odds_american": [-110, -110],
                "method": method,
            })
            assert resp.status_code == 200

    def test_multi_book_devig(self, client):
        resp = client.post("/api/calculator/devig/multi", json={
            "book_odds": [
                {"bookmaker": "pinnacle", "odds": [-108, -104]},
                {"bookmaker": "fanduel", "odds": [-110, -110]},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["methods"]) == 4
        assert "pinnacle" in data["books_used"]
        assert len(data["weighted_consensus"]) == 2

    def test_multi_devig_custom_methods(self, client):
        resp = client.post("/api/calculator/devig/multi", json={
            "book_odds": [{"bookmaker": "pinnacle", "odds": [-110, -110]}],
            "methods": ["multiplicative", "power"],
        })
        assert resp.status_code == 200
        assert len(resp.json()["methods"]) == 2


class TestBetGradesAPI:
    def test_grade_single_bet(self, client):
        resp = client.post("/api/bet-grade", json={
            "selection": "Lakers",
            "market": "h2h",
            "event": "Lakers vs Celtics",
            "edge_pct": 5.0,
            "best_odds_american": -110,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert 1 <= data["stars"] <= 5
        assert "components" in data
        assert "reasons" in data

    def test_grade_with_sharp_agreement(self, client):
        resp = client.post("/api/bet-grade", json={
            "selection": "Lakers",
            "market": "h2h",
            "event": "Test",
            "edge_pct": 5.0,
            "best_odds_american": -110,
            "sharp_book_agrees": True,
        })
        data = resp.json()
        assert data["components"]["sharp_agreement"] > 0

    def test_graded_edges_endpoint(self, client):
        resp = client.get("/api/bet-grades")
        assert resp.status_code == 200
        data = resp.json()
        assert "grades" in data
        assert "total" in data


class TestBacktestAPI:
    def test_basic_backtest(self, client):
        resp = client.post("/api/backtest", json={
            "strategy_name": "Test Strategy",
            "starting_bankroll": 10000,
            "stake_type": "flat",
            "stake_amount": 100,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy_name"] == "Test Strategy"
        assert data["grade"] in ("A", "B", "C", "D", "F")
        assert "equity_curve" in data
        assert "total_bets" in data
        assert "roi_pct" in data

    def test_backtest_with_filters(self, client):
        resp = client.post("/api/backtest", json={
            "min_edge": 2.0,
            "min_odds": -200,
            "max_odds": 300,
        })
        assert resp.status_code == 200

    def test_backtest_kelly(self, client):
        resp = client.post("/api/backtest", json={
            "stake_type": "kelly",
            "stake_amount": 50,
        })
        assert resp.status_code == 200


class TestPublicMoneyAPI:
    def test_public_money_not_found(self, client):
        resp = client.get("/api/public-money/nonexistent_event")
        assert resp.status_code == 404
