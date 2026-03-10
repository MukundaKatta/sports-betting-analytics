"""API tests for v2.1 features: multibook, limits, portfolio, splits, notifications."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app)


class TestMultibookAPI:
    def test_get_balances_empty(self):
        resp = client.get("/api/multibook/balances")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_balance" in data
        assert "books" in data

    def test_upsert_and_get_balance(self):
        # Add a book
        resp = client.post("/api/multibook/balances", json={
            "sportsbook": "test_book",
            "balance": 500.0,
            "deposited": 400.0,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

        # Verify it shows up
        resp = client.get("/api/multibook/balances")
        data = resp.json()
        assert data["book_count"] >= 1

        # Clean up
        client.delete("/api/multibook/balances/test_book")

    def test_delete_book(self):
        client.post("/api/multibook/balances", json={
            "sportsbook": "delete_me",
            "balance": 100.0,
        })
        resp = client.delete("/api/multibook/balances/delete_me")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_balance_history(self):
        resp = client.get("/api/multibook/history")
        assert resp.status_code == 200


class TestAccountLimitsAPI:
    def test_get_limits_empty(self):
        resp = client.get("/api/account-limits")
        assert resp.status_code == 200
        data = resp.json()
        assert "limits" in data
        assert "health_score" in data
        assert "tips" in data

    def test_upsert_and_get_limit(self):
        resp = client.post("/api/account-limits", json={
            "sportsbook": "test_limited_book",
            "limit_type": "stake_reduced",
            "severity": "medium",
            "max_stake": 50.0,
            "notes": "Props limited",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

        # Clean up
        client.delete("/api/account-limits/test_limited_book")

    def test_limiting_risk(self):
        resp = client.get("/api/account-limits/risk")
        assert resp.status_code == 200


class TestNotificationsAPI:
    def test_get_rules_empty(self):
        resp = client.get("/api/notification-rules")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_and_delete_rule(self):
        resp = client.post("/api/notification-rules", json={
            "name": "Test Rule",
            "rule_type": "ev_threshold",
            "min_ev": 5.0,
        })
        assert resp.status_code == 200
        rule_id = resp.json()["id"]

        # Toggle
        resp = client.post(f"/api/notification-rules/{rule_id}/toggle")
        assert resp.status_code == 200

        # Delete
        resp = client.delete(f"/api/notification-rules/{rule_id}")
        assert resp.status_code == 200


class TestCalibrationAPI:
    def test_calibration_endpoint(self):
        resp = client.get("/api/analytics/calibration")
        assert resp.status_code == 200
        data = resp.json()
        assert "calibration" in data
        assert "total_bets" in data


class TestBetImportAPI:
    def test_import_json(self):
        resp = client.post("/api/bets/import", json={
            "bets": [
                {
                    "selection": "Test Bet",
                    "odds_american": 150,
                    "stake": 25.0,
                    "bookmaker": "test",
                    "status": "pending",
                },
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1

    def test_import_empty(self):
        resp = client.post("/api/bets/import", json={"bets": []})
        assert resp.status_code == 200
        assert resp.json()["imported"] == 0

    def test_import_invalid_bet(self):
        resp = client.post("/api/bets/import", json={
            "bets": [{"selection": "", "odds_american": 0}],
        })
        assert resp.status_code == 200
        assert resp.json()["imported"] == 0
        assert len(resp.json()["errors"]) > 0


class TestSplitsAPI:
    def test_splits_unknown_player(self):
        resp = client.get("/api/splits/UnknownPlayer12345?stat=points")
        assert resp.status_code == 404

    def test_splits_invalid_stat(self):
        resp = client.get("/api/splits/AnyPlayer?stat=invalid_stat")
        assert resp.status_code == 404


class TestNewPageRoutes:
    def test_multibook_page(self):
        resp = client.get("/multibook")
        assert resp.status_code == 200
        assert "Multi-Book" in resp.text

    def test_account_limits_page(self):
        resp = client.get("/account-limits")
        assert resp.status_code == 200
        assert "Account Limits" in resp.text

    def test_portfolio_page(self):
        resp = client.get("/portfolio")
        assert resp.status_code == 200
        assert "Portfolio" in resp.text

    def test_bet_import_page(self):
        resp = client.get("/bet-import")
        assert resp.status_code == 200
        assert "Import" in resp.text

    def test_notifications_page(self):
        resp = client.get("/notifications")
        assert resp.status_code == 200
        assert "Notification" in resp.text
