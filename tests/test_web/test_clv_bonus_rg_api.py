"""Tests for CLV, Bonus Converter, and Responsible Gambling API endpoints."""

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app)


class TestCLVCalculateEndpoint:
    def test_positive_clv(self):
        resp = client.post("/api/clv/calculate", json={
            "opening_odds": -110, "closing_odds": -120
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["clv_percentage"] > 0
        assert data["beat_close"] is True

    def test_negative_clv(self):
        resp = client.post("/api/clv/calculate", json={
            "opening_odds": -120, "closing_odds": -110
        })
        assert resp.status_code == 200
        assert resp.json()["clv_percentage"] < 0

    def test_invalid_zero_odds(self):
        resp = client.post("/api/clv/calculate", json={
            "opening_odds": 0, "closing_odds": -110
        })
        assert resp.status_code == 422

    def test_plus_odds(self):
        resp = client.post("/api/clv/calculate", json={
            "opening_odds": 200, "closing_odds": 180
        })
        assert resp.status_code == 200
        assert resp.json()["clv_percentage"] > 0


class TestCLVDashboardEndpoint:
    def test_dashboard_returns_200(self):
        resp = client.get("/api/clv/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_bets_tracked" in data
        assert "avg_clv_pct" in data
        assert "assessment" in data

    def test_dashboard_has_metrics(self):
        resp = client.get("/api/clv/dashboard")
        data = resp.json()
        assert "total_bets_tracked" in data
        assert isinstance(data["total_bets_tracked"], int)


class TestBonusConvertEndpoint:
    def test_basic_conversion(self):
        resp = client.post("/api/bonus/convert", json={
            "bonus_amount": 100
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["bonus_amount"] == 100
        assert len(data["strategies"]) > 0
        assert "best_strategy" in data
        assert data["best_strategy"]["guaranteed_profit"] > 0

    def test_large_bonus(self):
        resp = client.post("/api/bonus/convert", json={
            "bonus_amount": 500, "conversion_pct": 80
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["bonus_amount"] == 500

    def test_invalid_zero_amount(self):
        resp = client.post("/api/bonus/convert", json={
            "bonus_amount": 0
        })
        assert resp.status_code == 422

    def test_invalid_negative(self):
        resp = client.post("/api/bonus/convert", json={
            "bonus_amount": -50
        })
        assert resp.status_code == 422

    def test_strategies_have_fields(self):
        resp = client.post("/api/bonus/convert", json={"bonus_amount": 100})
        data = resp.json()
        for s in data["strategies"]:
            assert "free_bet_odds" in s
            assert "hedge_amount" in s
            assert "guaranteed_profit" in s
            assert "conversion_rate" in s

    def test_tips_included(self):
        resp = client.post("/api/bonus/convert", json={"bonus_amount": 100})
        data = resp.json()
        assert len(data["tips"]) >= 3


class TestResponsibleGamblingEndpoint:
    def test_status_returns_200(self):
        resp = client.get("/api/responsible-gambling/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "today" in data
        assert "week" in data
        assert "month" in data
        assert "limits" in data
        assert "resources" in data
        assert "alerts" in data

    def test_has_resources(self):
        resp = client.get("/api/responsible-gambling/status")
        data = resp.json()
        assert len(data["resources"]) >= 2

    def test_limits_structure(self):
        resp = client.get("/api/responsible-gambling/status")
        data = resp.json()
        limits = data["limits"]
        assert "daily_loss" in limits
        assert "weekly_loss" in limits
        assert "daily_bets" in limits
        assert "max_stake_pct" in limits


class TestNewPageRoutes:
    def test_clv_dashboard_page(self):
        resp = client.get("/clv-dashboard")
        assert resp.status_code == 200

    def test_bonus_converter_page(self):
        resp = client.get("/bonus-converter")
        assert resp.status_code == 200

    def test_responsible_gambling_page(self):
        resp = client.get("/responsible-gambling")
        assert resp.status_code == 200
