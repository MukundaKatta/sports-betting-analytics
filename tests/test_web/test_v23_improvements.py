"""Tests for v2.3 improvements: responsible gambling, live analytics,
smart signals, natural language query, and reporting."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app)


# ── Responsible Gambling ────────────────────────────────────────────

class TestResponsibleGambling:
    def test_get_limits_empty(self):
        resp = client.get("/api/rg/limits")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_set_limit(self):
        resp = client.post("/api/rg/limits", json={
            "limit_type": "deposit",
            "amount": 500,
            "period": "daily",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit_type"] == "deposit"
        assert data["amount"] == 500

    def test_set_limit_invalid_type(self):
        resp = client.post("/api/rg/limits", json={
            "limit_type": "invalid",
            "amount": 100,
        })
        assert resp.status_code == 422

    def test_set_limit_negative_amount(self):
        resp = client.post("/api/rg/limits", json={
            "limit_type": "loss",
            "amount": -50,
        })
        assert resp.status_code == 422

    def test_check_limits(self):
        resp = client.get("/api/rg/limits/check")
        assert resp.status_code == 200
        data = resp.json()
        assert "checks" in data

    def test_remove_limit(self):
        # Set then remove
        client.post("/api/rg/limits", json={
            "limit_type": "wager",
            "amount": 1000,
            "period": "weekly",
        })
        resp = client.delete("/api/rg/limits?limit_type=wager&period=weekly")
        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"


class TestSessionTracking:
    def test_start_session(self):
        resp = client.post("/api/rg/sessions/start")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data

    def test_end_session(self):
        client.post("/api/rg/sessions/start")
        resp = client.post("/api/rg/sessions/end")
        assert resp.status_code == 200

    def test_session_stats(self):
        resp = client.get("/api/rg/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "today" in data
        assert "week" in data

    def test_cooldown_check(self):
        resp = client.get("/api/rg/cooldown")
        assert resp.status_code == 200
        data = resp.json()
        assert "active" in data

    def test_set_cooldown(self):
        resp = client.post("/api/rg/cooldown", json={"hours": 24})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cooldown_set"
        assert data["hours"] == 24

    def test_set_cooldown_invalid(self):
        resp = client.post("/api/rg/cooldown", json={"hours": 0})
        assert resp.status_code == 422


class TestBehavioralAnalysis:
    def test_behavioral_report(self):
        resp = client.get("/api/rg/behavior")
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_level" in data
        assert "score" in data
        assert "indicators" in data
        assert "recommendations" in data
        assert data["risk_level"] in ("low", "moderate", "high")

    def test_behavioral_report_service_direct(self):
        from sba.services.responsible_gambling import get_behavioral_report
        result = get_behavioral_report()
        assert isinstance(result, dict)
        assert "risk_level" in result


# ── Live Analytics ──────────────────────────────────────────────────

class TestLiveAnalytics:
    def test_live_games_summary(self):
        resp = client.get("/api/live/games")
        assert resp.status_code == 200
        data = resp.json()
        assert "active_games" in data
        assert "games" in data
        assert isinstance(data["games"], list)

    def test_live_game_analysis_not_found(self):
        resp = client.get("/api/live/game/nonexistent_event_123")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    def test_odds_velocity_not_found(self):
        resp = client.get("/api/live/velocity/nonexistent_event_123")
        assert resp.status_code == 200
        data = resp.json()
        assert "velocity" in data

    def test_odds_velocity_bounds(self):
        resp = client.get("/api/live/velocity/test?window=3")
        assert resp.status_code == 422

    def test_live_analytics_service_direct(self):
        from sba.services.live_analytics import get_live_games_summary
        result = get_live_games_summary()
        assert isinstance(result, dict)
        assert "active_games" in result

    def test_line_movement_analysis(self):
        from sba.services.live_analytics import _analyze_line_movements
        result = _analyze_line_movements([])
        assert result == []

    def test_momentum_detection(self):
        from sba.services.live_analytics import _detect_momentum
        event = {"home_team": "Lakers", "away_team": "Celtics"}
        result = _detect_momentum([], event)
        assert "team" in result
        assert "strength" in result


# ── Smart Signals ───────────────────────────────────────────────────

class TestSmartSignals:
    def test_scan_signals(self):
        resp = client.get("/api/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert "patterns_found" in data
        assert "active_signals" in data
        assert "patterns" in data

    def test_discover_patterns(self):
        resp = client.get("/api/signals/patterns?min_bets=3&min_roi=0")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_discover_patterns_bounds(self):
        resp = client.get("/api/signals/patterns?min_bets=1")
        assert resp.status_code == 422

    def test_pattern_detail(self):
        resp = client.get("/api/signals/pattern/market:h2h|sport:basketball_nba")
        assert resp.status_code == 200
        data = resp.json()
        assert "pattern" in data
        assert "total_bets" in data

    def test_odds_to_range(self):
        from sba.services.smart_signals import _odds_to_range
        assert _odds_to_range(250) == "longshot_200+"
        assert _odds_to_range(150) == "plus_100_200"
        assert _odds_to_range(-110) == "even_-120_+100"
        assert _odds_to_range(-150) == "favorite_-200_-120"
        assert _odds_to_range(-300) == "heavy_fav_-200"

    def test_smart_signals_service_direct(self):
        from sba.services.smart_signals import scan_signals
        result = scan_signals()
        assert isinstance(result, dict)
        assert "patterns_found" in result


# ── Natural Language Query ──────────────────────────────────────────

class TestNLQ:
    def test_ask_summary(self):
        resp = client.post("/api/ask", json={"question": "How am I doing?"})
        assert resp.status_code == 200
        data = resp.json()
        assert "intent" in data
        assert "answer" in data
        assert isinstance(data["answer"], str)

    def test_ask_win_rate(self):
        resp = client.post("/api/ask", json={"question": "What's my win rate?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "win_rate"

    def test_ask_roi(self):
        resp = client.post("/api/ask", json={"question": "Show me my ROI"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "roi"

    def test_ask_streak(self):
        resp = client.post("/api/ask", json={"question": "Am I on a streak?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "streak"

    def test_ask_period(self):
        resp = client.post("/api/ask", json={"question": "How did I do this week?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "performance_period"

    def test_ask_best_market(self):
        resp = client.post("/api/ask", json={"question": "What's my best market?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "best_market"

    def test_ask_bookmaker(self):
        resp = client.post("/api/ask", json={"question": "How am I doing at DraftKings?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "bookmaker_performance"

    def test_ask_unknown(self):
        resp = client.post("/api/ask", json={"question": "xyzzy"})
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data

    def test_ask_empty(self):
        resp = client.post("/api/ask", json={"question": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data

    def test_ask_recent_bets(self):
        resp = client.post("/api/ask", json={"question": "Show recent bets"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "recent_bets"

    def test_ask_pending(self):
        resp = client.post("/api/ask", json={"question": "Show pending bets"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "pending"

    def test_nlq_service_direct(self):
        from sba.services.nlq import query
        result = query("What's my record?")
        assert isinstance(result, dict)
        assert "answer" in result

    def test_keyword_fallback(self):
        from sba.services.nlq import _keyword_fallback
        result = _keyword_fallback("how's my profit", "how's my profit")
        assert result["intent"] == "keyword_match"


# ── Reporting ───────────────────────────────────────────────────────

class TestReporting:
    def test_daily_report(self):
        resp = client.get("/api/reports/daily")
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_type"] == "daily"
        assert "summary" in data
        assert "by_market" in data
        assert "bets" in data

    def test_daily_report_custom_date(self):
        resp = client.get("/api/reports/daily?date=2025-01-15")
        assert resp.status_code == 200
        data = resp.json()
        assert data["date"] == "2025-01-15"

    def test_weekly_report(self):
        resp = client.get("/api/reports/weekly")
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_type"] == "weekly"
        assert "summary" in data
        assert "daily_breakdown" in data

    def test_weekly_report_past(self):
        resp = client.get("/api/reports/weekly?weeks_ago=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_type"] == "weekly"

    def test_monthly_report(self):
        resp = client.get("/api/reports/monthly")
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_type"] == "monthly"
        assert "summary" in data
        assert "by_sport" in data

    def test_monthly_report_specific(self):
        resp = client.get("/api/reports/monthly?year=2025&month=6")
        assert resp.status_code == 200
        data = resp.json()
        assert data["year"] == 2025
        assert data["month"] == 6

    def test_export_bets(self):
        resp = client.get("/api/reports/export")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_bets" in data
        assert "summary" in data
        assert "bets" in data

    def test_export_with_filters(self):
        resp = client.get("/api/reports/export?status=won&start_date=2025-01-01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["filters"]["status"] == "won"

    def test_reporting_service_direct(self):
        from sba.services.reporting import generate_daily_report
        result = generate_daily_report()
        assert isinstance(result, dict)
        assert "summary" in result


# ── Schema Updates ──────────────────────────────────────────────────

class TestV23Schema:
    def test_schema_has_rg_tables(self):
        from sba.data.db.schema import SCHEMA_SQL
        assert "rg_limits" in SCHEMA_SQL
        assert "rg_sessions" in SCHEMA_SQL
        assert "idx_rg_sessions_date" in SCHEMA_SQL

    def test_version_bumped(self):
        assert app.version >= "2.3.0"
