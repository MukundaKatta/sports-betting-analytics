"""Tests for Phase 2-4 API endpoints: bankroll, CLV, sharp money, community, tags/notes."""

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestBankrollAPI:
    def test_get_bankroll_empty(self, client):
        resp = client.get("/api/bankroll")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_balance" in data
        assert "total_profit" in data

    def test_initialize_bankroll(self, client):
        resp = client.post("/api/bankroll/initialize", json={"amount": 5000, "reason": "start"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["balance"] == 5000

    def test_deposit(self, client):
        # Initialize first
        client.post("/api/bankroll/initialize", json={"amount": 1000})
        resp = client.post("/api/bankroll/deposit", json={"amount": 500, "reason": "bonus"})
        assert resp.status_code == 200
        assert resp.json()["deposited"] == 500

    def test_withdraw(self, client):
        client.post("/api/bankroll/initialize", json={"amount": 1000})
        resp = client.post("/api/bankroll/withdraw", json={"amount": 200})
        assert resp.status_code == 200
        assert resp.json()["withdrawn"] == 200

    def test_daily_pnl(self, client):
        resp = client.get("/api/bankroll/daily")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestCLVAPI:
    def _create_bet(self, client):
        from sba.data.db import get_connection, init_db
        init_db()
        with get_connection() as conn:
            # Ensure event exists
            conn.execute("""
                INSERT OR IGNORE INTO events (id, sport, home_team, away_team, commence_time)
                VALUES ('clv_test', 'nba', 'Team A', 'Team B', '2025-03-15')
            """)
            cursor = conn.execute("""
                INSERT INTO bets (event_id, market, selection, odds_american, odds_decimal,
                                  model_probability, expected_value, kelly_fraction,
                                  recommended_stake, bookmaker)
                VALUES ('clv_test', 'h2h', 'Team A', -110, 1.909, 0.55, 0.05, 0.03, 50, 'fanduel')
            """)
            return cursor.lastrowid

    def test_record_clv(self, client):
        bet_id = self._create_bet(client)
        resp = client.post("/api/clv/record", json={
            "bet_id": bet_id, "closing_odds_american": -120,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "clv_percentage" in data
        assert "beat_closing" in data

    def test_clv_summary_empty(self, client):
        resp = client.get("/api/clv/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_tracked" in data

    def test_clv_not_found_bet(self, client):
        resp = client.post("/api/clv/record", json={
            "bet_id": 99999, "closing_odds_american": -110,
        })
        assert resp.status_code == 404


class TestSharpMoneyAPI:
    def test_get_all_sharp_moves(self, client):
        resp = client.get("/api/sharp-money")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_analyze_event(self, client):
        resp = client.get("/api/sharp-money/test_event_123?market=h2h")
        assert resp.status_code == 200
        data = resp.json()
        assert "signals" in data
        assert data["event_id"] == "test_event_123"


class TestLeaderboardAPI:
    def test_get_leaderboard_empty(self, client):
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_register_user(self, client):
        resp = client.post("/api/leaderboard/register", json={
            "username": "testuser_lb", "display_name": "Test User",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] in ("registered", "already_exists")

    def test_register_duplicate(self, client):
        client.post("/api/leaderboard/register", json={"username": "dup_user"})
        resp = client.post("/api/leaderboard/register", json={"username": "dup_user"})
        assert resp.json()["status"] == "already_exists"


class TestPicksAPI:
    def _setup_user(self, client):
        client.post("/api/leaderboard/register", json={
            "username": "picker_test", "display_name": "Picker",
        })

    def test_submit_pick(self, client):
        self._setup_user(client)
        resp = client.post("/api/picks", json={
            "username": "picker_test",
            "event_id": "test_event",
            "market": "h2h",
            "selection": "Lakers",
            "odds_american": -110,
            "confidence": "medium",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "submitted"

    def test_get_picks(self, client):
        resp = client.get("/api/picks?limit=10")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_submit_pick_unregistered(self, client):
        resp = client.post("/api/picks", json={
            "username": "nobody_9999",
            "event_id": "test",
            "market": "h2h",
            "selection": "Team",
            "odds_american": -110,
        })
        assert resp.status_code == 400

    def test_settle_pick(self, client):
        self._setup_user(client)
        create = client.post("/api/picks", json={
            "username": "picker_test", "event_id": "ev1",
            "market": "h2h", "selection": "Team A", "odds_american": 150,
        })
        pick_id = create.json()["id"]
        resp = client.put(f"/api/picks/{pick_id}/settle", json={
            "status": "won", "profit_loss": 150.0,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "won"


class TestAlertRulesAPI:
    def test_create_rule(self, client):
        resp = client.post("/api/alert-rules", json={
            "rule_type": "ev_threshold",
            "condition_json": '{"min_ev": 0.05}',
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "created"

    def test_invalid_rule_type(self, client):
        resp = client.post("/api/alert-rules", json={
            "rule_type": "invalid_type",
        })
        assert resp.status_code == 400

    def test_get_rules(self, client):
        resp = client.get("/api/alert-rules")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_toggle_rule(self, client):
        create = client.post("/api/alert-rules", json={"rule_type": "arb_detected"})
        rule_id = create.json()["id"]
        resp = client.put(f"/api/alert-rules/{rule_id}/toggle")
        assert resp.status_code == 200
        assert "enabled" in resp.json()

    def test_delete_rule(self, client):
        create = client.post("/api/alert-rules", json={"rule_type": "line_movement"})
        rule_id = create.json()["id"]
        resp = client.delete(f"/api/alert-rules/{rule_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


class TestBetTagsNotes:
    def _create_bet(self, client):
        from sba.data.db import get_connection, init_db
        init_db()
        with get_connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO events (id, sport, home_team, away_team, commence_time)
                VALUES ('tag_test', 'nba', 'A', 'B', '2025-03-15')
            """)
            cursor = conn.execute("""
                INSERT INTO bets (event_id, market, selection, odds_american, odds_decimal,
                                  model_probability, expected_value, kelly_fraction,
                                  recommended_stake, bookmaker)
                VALUES ('tag_test', 'h2h', 'A', -110, 1.909, 0.55, 0.03, 0.02, 25, 'dk')
            """)
            return cursor.lastrowid

    def test_add_tag(self, client):
        bet_id = self._create_bet(client)
        resp = client.post(f"/api/bets/{bet_id}/tags", json={"tag": "sharp"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "added"

    def test_get_tags(self, client):
        bet_id = self._create_bet(client)
        client.post(f"/api/bets/{bet_id}/tags", json={"tag": "value"})
        resp = client.get(f"/api/bets/{bet_id}/tags")
        assert resp.status_code == 200
        assert "value" in resp.json()

    def test_remove_tag(self, client):
        bet_id = self._create_bet(client)
        client.post(f"/api/bets/{bet_id}/tags", json={"tag": "remove_me"})
        resp = client.delete(f"/api/bets/{bet_id}/tags/remove_me")
        assert resp.status_code == 200

    def test_add_note(self, client):
        bet_id = self._create_bet(client)
        resp = client.post(f"/api/bets/{bet_id}/notes", json={"note": "Test analysis"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "added"

    def test_get_notes(self, client):
        bet_id = self._create_bet(client)
        client.post(f"/api/bets/{bet_id}/notes", json={"note": "My note"})
        resp = client.get(f"/api/bets/{bet_id}/notes")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
        assert resp.json()[0]["note"] == "My note"
