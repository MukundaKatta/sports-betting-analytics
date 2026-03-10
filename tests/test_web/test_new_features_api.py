"""Tests for new feature API endpoints: SGP, power ratings, promo, odds screen, sports."""

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestSGPBuilder:
    def test_sgp_two_legs(self, client):
        resp = client.post("/api/calculator/sgp", json={
            "legs": [
                {"market": "player_points", "direction": "over", "selection": "LeBron points", "odds_american": -110},
                {"market": "player_threes", "direction": "over", "selection": "LeBron threes", "odds_american": -110},
            ],
            "stake": 100,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["num_legs"] == 2
        assert "naive_odds_american" in data
        assert "correlated_odds_american" in data
        assert "correlation_adjustment_pct" in data
        assert data["stake"] == 100
        assert data["payout"] > 0

    def test_sgp_with_player_name(self, client):
        resp = client.post("/api/calculator/sgp", json={
            "legs": [
                {"market": "player_points", "direction": "over", "selection": "pts", "odds_american": -110, "player_name": "LeBron"},
                {"market": "player_assists", "direction": "over", "selection": "ast", "odds_american": 120, "player_name": "LeBron"},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["legs"][0]["player"] == "LeBron"

    def test_sgp_requires_two_legs(self, client):
        resp = client.post("/api/calculator/sgp", json={
            "legs": [
                {"market": "player_points", "direction": "over", "selection": "pts", "odds_american": -110},
            ],
        })
        assert resp.status_code == 400

    def test_sgp_three_legs(self, client):
        resp = client.post("/api/calculator/sgp", json={
            "legs": [
                {"market": "player_points", "direction": "over", "selection": "pts", "odds_american": -110},
                {"market": "player_assists", "direction": "over", "selection": "ast", "odds_american": 120},
                {"market": "player_rebounds", "direction": "over", "selection": "reb", "odds_american": -105},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["num_legs"] == 3

    def test_sgp_correlations_in_response(self, client):
        resp = client.post("/api/calculator/sgp", json={
            "legs": [
                {"market": "player_points", "direction": "over", "selection": "pts", "odds_american": -110},
                {"market": "player_threes", "direction": "over", "selection": "3s", "odds_american": -110},
            ],
        })
        data = resp.json()
        assert len(data["correlations"]) > 0
        assert data["correlation_adjustment_pct"] != 0


class TestCorrelationMatrix:
    def test_get_correlations(self, client):
        resp = client.get("/api/correlations")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "market_a" in data[0]
        assert "correlation" in data[0]

    def test_correlations_nonzero(self, client):
        resp = client.get("/api/correlations")
        data = resp.json()
        for entry in data:
            assert entry["correlation"] != 0


class TestPowerRatings:
    def test_get_ratings_empty_db(self, client):
        resp = client.get("/api/power-ratings")
        assert resp.status_code == 200
        data = resp.json()
        assert "ratings" in data
        assert "sport" in data
        assert data["sport"] == "basketball_nba"

    def test_get_ratings_with_sport(self, client):
        resp = client.get("/api/power-ratings?sport=americanfootball_nfl")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sport"] == "americanfootball_nfl"


class TestMatchup:
    def test_matchup_empty_db(self, client):
        resp = client.get("/api/matchup?home=Lakers&away=Celtics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["home_team"] == "Lakers"
        assert data["away_team"] == "Celtics"
        assert "home_win_prob" in data
        assert "predicted_spread" in data

    def test_matchup_with_spread(self, client):
        resp = client.get("/api/matchup?home=Lakers&away=Celtics&spread=-3.5")
        assert resp.status_code == 200
        data = resp.json()
        assert "home_edge" in data


class TestPromoOptimizer:
    def test_risk_free_bet(self, client):
        resp = client.post("/api/calculator/promo", json={
            "promo_type": "risk_free",
            "amount": 1000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["expected_value"] > 0
        assert "strategy" in data
        assert data["conversion_rate"] > 0

    def test_deposit_match(self, client):
        resp = client.post("/api/calculator/promo", json={
            "promo_type": "deposit_match",
            "amount": 500,
            "rollover": 1.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["expected_value"] > 0

    def test_profit_boost(self, client):
        resp = client.post("/api/calculator/promo", json={
            "promo_type": "profit_boost",
            "amount": 100,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "strategy" in data

    def test_free_bet(self, client):
        resp = client.post("/api/calculator/promo", json={
            "promo_type": "free_bet",
            "amount": 200,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversion_rate"] > 0

    def test_unknown_promo_type(self, client):
        resp = client.post("/api/calculator/promo", json={
            "promo_type": "unknown_type",
            "amount": 100,
        })
        assert resp.status_code == 400


class TestOddsScreen:
    def test_odds_screen_empty_db(self, client):
        resp = client.get("/api/odds-screen")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "sport" in data
        assert "market" in data

    def test_odds_screen_with_market(self, client):
        resp = client.get("/api/odds-screen?market=spreads")
        assert resp.status_code == 200
        data = resp.json()
        assert data["market"] == "spreads"


class TestConsensus:
    def test_consensus_no_data(self, client):
        resp = client.get("/api/consensus/nonexistent_event")
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == "nonexistent_event"
        assert data["markets"] == {}


class TestSports:
    def test_get_sports(self, client):
        resp = client.get("/api/sports")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Should include known sports even with empty DB
        keys = [s["key"] for s in data]
        assert "basketball_nba" in keys
        assert "americanfootball_nfl" in keys

    def test_sports_have_required_fields(self, client):
        resp = client.get("/api/sports")
        data = resp.json()
        for sport in data:
            assert "key" in sport
            assert "name" in sport
            assert "event_count" in sport
