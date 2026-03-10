"""Tests for calculator API endpoints (parlay, free bet, no-vig)."""

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestParlayCalculator:
    def test_two_leg_parlay(self, client):
        resp = client.post("/api/calculator/parlay", json={
            "legs": [
                {"odds_american": -110, "description": "Leg 1"},
                {"odds_american": 150, "description": "Leg 2"},
            ],
            "stake": 100,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["num_legs"] == 2
        assert data["combined_odds_decimal"] > 1
        assert data["payout"] > 100
        assert data["profit"] > 0

    def test_parlay_needs_two_legs(self, client):
        resp = client.post("/api/calculator/parlay", json={
            "legs": [{"odds_american": -110}],
            "stake": 100,
        })
        assert resp.status_code == 400

    def test_three_leg_parlay(self, client):
        resp = client.post("/api/calculator/parlay", json={
            "legs": [
                {"odds_american": -110},
                {"odds_american": -110},
                {"odds_american": 200},
            ],
            "stake": 50,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["num_legs"] == 3
        assert data["stake"] == 50

    def test_parlay_combined_probability(self, client):
        resp = client.post("/api/calculator/parlay", json={
            "legs": [
                {"odds_american": 100},  # 50% implied
                {"odds_american": 100},  # 50% implied
            ],
            "stake": 100,
        })
        data = resp.json()
        # Combined decimal = 2.0 * 2.0 = 4.0, prob = 0.25
        assert abs(data["combined_probability"] - 0.25) < 0.01


class TestFreeBetConverter:
    def test_basic_conversion(self, client):
        resp = client.post("/api/calculator/freebet", json={
            "free_bet_amount": 100,
            "free_bet_odds": 200,
            "hedge_odds": -200,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["hedge_stake"] > 0
        assert data["guaranteed_profit"] > 0
        assert data["conversion_rate"] > 0

    def test_conversion_rate_reasonable(self, client):
        """Conversion rate should be between 0 and 100%."""
        resp = client.post("/api/calculator/freebet", json={
            "free_bet_amount": 100,
            "free_bet_odds": 300,
            "hedge_odds": -300,
        })
        data = resp.json()
        assert 0 < data["conversion_rate"] < 100

    def test_higher_odds_better_conversion(self, client):
        """Higher free bet odds should generally yield better conversion."""
        resp1 = client.post("/api/calculator/freebet", json={
            "free_bet_amount": 100, "free_bet_odds": 200, "hedge_odds": -150,
        })
        resp2 = client.post("/api/calculator/freebet", json={
            "free_bet_amount": 100, "free_bet_odds": 400, "hedge_odds": -150,
        })
        d1 = resp1.json()
        d2 = resp2.json()
        assert d2["guaranteed_profit"] > d1["guaranteed_profit"]


class TestNoVigCalculator:
    def test_standard_vig_removal(self, client):
        resp = client.post("/api/calculator/novig", json={
            "outcomes": [
                {"name": "Team A", "odds_american": -110},
                {"name": "Team B", "odds_american": -110},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["vig_percentage"] > 0
        # Fair probabilities should sum to ~100%
        total_fair = sum(o["fair_probability"] for o in data["outcomes"])
        assert abs(total_fair - 100.0) < 0.1

    def test_needs_two_outcomes(self, client):
        resp = client.post("/api/calculator/novig", json={
            "outcomes": [{"name": "Team A", "odds_american": -110}],
        })
        assert resp.status_code == 400

    def test_even_odds_no_vig(self, client):
        """Even money (+100/+100) has zero vig."""
        resp = client.post("/api/calculator/novig", json={
            "outcomes": [
                {"name": "A", "odds_american": 100},
                {"name": "B", "odds_american": 100},
            ],
        })
        data = resp.json()
        assert abs(data["vig_percentage"]) < 0.1
        assert abs(data["total_implied_probability"] - 100.0) < 0.1

    def test_fair_odds_returned(self, client):
        resp = client.post("/api/calculator/novig", json={
            "outcomes": [
                {"name": "Fav", "odds_american": -150},
                {"name": "Dog", "odds_american": 130},
            ],
        })
        data = resp.json()
        assert len(data["outcomes"]) == 2
        for o in data["outcomes"]:
            assert "fair_odds_american" in o
            assert "fair_probability" in o
            assert o["fair_probability"] > 0


class TestHedgeCalculator:
    def test_basic_hedge(self, client):
        resp = client.post("/api/calculator/hedge", json={
            "original_odds": 200,
            "original_stake": 100,
            "hedge_odds": -150,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["hedge_stake"] > 0
        assert data["total_invested"] > 100
