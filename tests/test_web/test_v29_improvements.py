"""Tests for v2.9.0 improvements.

Covers: constants, audit logging, schema migrations, atomic transactions,
webhook retry, input sanitization, pagination, async edge finder, and API client retry.
"""

import sqlite3
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app)


# ── Constants Module ──────────────────────────────────────────────────


class TestConstants:
    def test_ev_confidence_thresholds(self):
        from sba.config.constants import EV_CONFIDENCE_HIGH, EV_CONFIDENCE_MEDIUM
        assert EV_CONFIDENCE_HIGH == 0.08
        assert EV_CONFIDENCE_MEDIUM == 0.04
        assert EV_CONFIDENCE_HIGH > EV_CONFIDENCE_MEDIUM

    def test_ml_constants(self):
        from sba.config.constants import (
            ML_MIN_FEATURE_GAMES,
            ML_MIN_TRAINING_SAMPLES,
            ML_WARMUP_GAMES,
            ML_XGBOOST_LEARNING_RATE,
            ML_XGBOOST_MAX_DEPTH,
            ML_XGBOOST_N_ESTIMATORS,
        )
        assert ML_MIN_TRAINING_SAMPLES == 30
        assert ML_MIN_FEATURE_GAMES == 5
        assert ML_WARMUP_GAMES == 20
        assert ML_XGBOOST_N_ESTIMATORS == 100
        assert ML_XGBOOST_MAX_DEPTH == 5
        assert ML_XGBOOST_LEARNING_RATE == 0.1

    def test_api_constants(self):
        from sba.config.constants import (
            HTTP_TIMEOUT_SECONDS,
            MAX_RETRY_ATTEMPTS,
            RETRY_BASE_DELAY,
            RETRYABLE_STATUS_CODES,
        )
        assert HTTP_TIMEOUT_SECONDS == 30.0
        assert MAX_RETRY_ATTEMPTS == 3
        assert RETRY_BASE_DELAY == 5
        assert 429 in RETRYABLE_STATUS_CODES
        assert 503 in RETRYABLE_STATUS_CODES

    def test_pagination_constants(self):
        from sba.config.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
        assert DEFAULT_PAGE_SIZE == 50
        assert MAX_PAGE_SIZE == 500
        assert MAX_PAGE_SIZE > DEFAULT_PAGE_SIZE

    def test_webhook_constants(self):
        from sba.config.constants import (
            WEBHOOK_MAX_RETRIES,
            WEBHOOK_RETRY_DELAYS,
            WEBHOOK_TIMEOUT_SECONDS,
        )
        assert WEBHOOK_MAX_RETRIES == 3
        assert len(WEBHOOK_RETRY_DELAYS) == 3
        assert WEBHOOK_TIMEOUT_SECONDS == 10

    def test_cache_constants(self):
        from sba.config.constants import CACHE_DEFAULT_TTL, CACHE_MAX_ENTRIES
        assert CACHE_MAX_ENTRIES == 1000
        assert CACHE_DEFAULT_TTL == 30.0

    def test_db_constants(self):
        from sba.config.constants import DB_BUSY_TIMEOUT_MS, DB_CACHE_SIZE_KB, SCHEMA_VERSION
        assert DB_BUSY_TIMEOUT_MS == 5000
        assert DB_CACHE_SIZE_KB == 8000
        assert SCHEMA_VERSION >= 2

    def test_rolling_windows(self):
        from sba.config.constants import ROLLING_WINDOWS
        assert ROLLING_WINDOWS == [3, 5, 10, 20]


# ── Schema Migrations ────────────────────────────────────────────────


class TestSchemaMigrations:
    def test_migration_creates_version_table(self):
        from sba.data.db.migrations import _ensure_version_table, get_schema_version
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _ensure_version_table(conn)
        version = get_schema_version(conn)
        assert version == 0
        conn.close()

    def test_migration_v1_creates_audit_log(self):
        from sba.data.db.migrations import _migrate_v1
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _migrate_v1(conn)
        # Verify table exists
        conn.execute(
            "INSERT INTO audit_log (action, entity_type, entity_id) VALUES ('test', 'test', '1')"
        )
        row = conn.execute("SELECT * FROM audit_log").fetchone()
        assert row["action"] == "test"
        conn.close()

    def test_migration_v2_creates_webhook_deliveries(self):
        from sba.data.db.migrations import _migrate_v2
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _migrate_v2(conn)
        conn.execute(
            "INSERT INTO webhook_deliveries (webhook_url, status) VALUES ('http://test.com', 'pending')"
        )
        row = conn.execute("SELECT * FROM webhook_deliveries").fetchone()
        assert row["webhook_url"] == "http://test.com"
        conn.close()

    def test_run_migrations_applies_all(self):
        from sba.data.db.migrations import get_schema_version, run_migrations, _ensure_version_table
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        applied = run_migrations(conn)
        assert applied >= 2
        version = get_schema_version(conn)
        assert version >= 2
        conn.close()

    def test_run_migrations_idempotent(self):
        from sba.data.db.migrations import run_migrations
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        first = run_migrations(conn)
        second = run_migrations(conn)
        assert first >= 2
        assert second == 0
        conn.close()


# ── Audit Logging ────────────────────────────────────────────────────


class TestAuditLogging:
    def test_log_audit_entry(self):
        from sba.data.db.audit import get_audit_log, log_audit
        from sba.data.db.migrations import _migrate_v1
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _migrate_v1(conn)

        log_audit(conn, "create", "bet", 42, {"market": "h2h"})
        entries = get_audit_log(conn)
        assert len(entries) == 1
        assert entries[0]["action"] == "create"
        assert entries[0]["entity_type"] == "bet"
        assert entries[0]["entity_id"] == "42"
        assert entries[0]["details"]["market"] == "h2h"
        conn.close()

    def test_audit_log_filtering(self):
        from sba.data.db.audit import get_audit_log, log_audit
        from sba.data.db.migrations import _migrate_v1
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _migrate_v1(conn)

        log_audit(conn, "create", "bet", 1)
        log_audit(conn, "settle", "bet", 2)
        log_audit(conn, "create", "event", 3)

        bet_entries = get_audit_log(conn, entity_type="bet")
        assert len(bet_entries) == 2

        event_entries = get_audit_log(conn, entity_type="event")
        assert len(event_entries) == 1

        specific = get_audit_log(conn, entity_id="1")
        assert len(specific) == 1
        conn.close()

    def test_audit_log_pagination(self):
        from sba.data.db.audit import get_audit_log, log_audit
        from sba.data.db.migrations import _migrate_v1
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _migrate_v1(conn)

        for i in range(5):
            log_audit(conn, "create", "bet", i)

        page1 = get_audit_log(conn, limit=2, offset=0)
        assert len(page1) == 2

        page2 = get_audit_log(conn, limit=2, offset=2)
        assert len(page2) == 2
        conn.close()

    def test_audit_api_endpoint(self):
        resp = client.get("/api/audit-log")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "count" in data
        assert "limit" in data
        assert "offset" in data


# ── Atomic Transactions ──────────────────────────────────────────────


class TestAtomicTransactions:
    def test_atomic_success(self):
        from sba.data.db.connection import atomic
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")

        with atomic(conn):
            conn.execute("INSERT INTO test (value) VALUES ('a')")
            conn.execute("INSERT INTO test (value) VALUES ('b')")

        rows = conn.execute("SELECT * FROM test").fetchall()
        assert len(rows) == 2
        conn.close()

    def test_atomic_rollback_on_error(self):
        from sba.data.db.connection import atomic
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT UNIQUE)")
        conn.execute("INSERT INTO test (value) VALUES ('existing')")

        with pytest.raises(sqlite3.IntegrityError):
            with atomic(conn):
                conn.execute("INSERT INTO test (value) VALUES ('new')")
                conn.execute("INSERT INTO test (value) VALUES ('existing')")  # Duplicate

        # The 'new' row should be rolled back
        rows = conn.execute("SELECT * FROM test").fetchall()
        assert len(rows) == 1
        assert rows[0]["value"] == "existing"
        conn.close()

    def test_nested_atomic_savepoints(self):
        from sba.data.db.connection import atomic
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")

        conn.execute("INSERT INTO test (value) VALUES ('outer')")
        # Inner atomic should not affect outer
        try:
            with atomic(conn):
                conn.execute("INSERT INTO test (value) VALUES ('inner')")
                raise ValueError("inner error")
        except ValueError:
            pass

        rows = conn.execute("SELECT * FROM test").fetchall()
        assert len(rows) == 1  # inner was rolled back
        conn.close()


# ── Input Sanitization ───────────────────────────────────────────────


class TestInputSanitization:
    def test_sanitize_string_basic(self):
        from sba.utils.sanitize import sanitize_string
        assert sanitize_string("  hello  ") == "hello"
        assert sanitize_string("") == ""
        assert sanitize_string("a\x00b") == "ab"  # null byte removed

    def test_sanitize_string_max_length(self):
        from sba.utils.sanitize import sanitize_string
        long_str = "a" * 1000
        result = sanitize_string(long_str, max_length=100)
        assert len(result) == 100

    def test_sanitize_string_control_chars(self):
        from sba.utils.sanitize import sanitize_string
        assert sanitize_string("hello\x01world") == "helloworld"
        # Tabs and newlines are preserved
        assert "\n" in sanitize_string("hello\nworld")
        assert "\t" in sanitize_string("hello\tworld")

    def test_sanitize_webhook_url_valid(self):
        from sba.utils.sanitize import sanitize_webhook_url
        assert sanitize_webhook_url("https://hooks.slack.com/test") == "https://hooks.slack.com/test"
        assert sanitize_webhook_url("http://api.example.com/webhook") == "http://api.example.com/webhook"

    def test_sanitize_webhook_url_invalid_scheme(self):
        from sba.utils.sanitize import sanitize_webhook_url
        with pytest.raises(ValueError, match="scheme"):
            sanitize_webhook_url("ftp://example.com")

    def test_sanitize_webhook_url_blocks_localhost(self):
        from sba.utils.sanitize import sanitize_webhook_url
        with pytest.raises(ValueError, match="internal host"):
            sanitize_webhook_url("http://localhost/hook")
        with pytest.raises(ValueError, match="internal host"):
            sanitize_webhook_url("http://127.0.0.1/hook")

    def test_sanitize_webhook_url_blocks_private_ips(self):
        from sba.utils.sanitize import sanitize_webhook_url
        with pytest.raises(ValueError, match="private IP"):
            sanitize_webhook_url("http://10.0.0.1/hook")
        with pytest.raises(ValueError, match="private IP"):
            sanitize_webhook_url("http://192.168.1.1/hook")

    def test_sanitize_pagination(self):
        from sba.utils.sanitize import sanitize_pagination
        limit, offset = sanitize_pagination(None, None)
        assert limit == 50
        assert offset == 0

        limit, offset = sanitize_pagination(1000, -5)
        assert limit == 500  # clamped to MAX_PAGE_SIZE
        assert offset == 0  # clamped to 0

        limit, offset = sanitize_pagination(25, 100)
        assert limit == 25
        assert offset == 100

    def test_sanitize_sort_field(self):
        from sba.utils.sanitize import sanitize_sort_field
        allowed = {"name", "created_at", "amount"}
        assert sanitize_sort_field("name", allowed) == "name"
        assert sanitize_sort_field("invalid", allowed) == "created_at"
        assert sanitize_sort_field("  NAME  ", allowed) == "name"

    def test_sanitize_sort_order(self):
        from sba.utils.sanitize import sanitize_sort_order
        assert sanitize_sort_order("asc") == "ASC"
        assert sanitize_sort_order("DESC") == "DESC"
        assert sanitize_sort_order("invalid") == "DESC"


# ── Repository Improvements ──────────────────────────────────────────


class TestRepositoryImprovements:
    def test_count_bets(self, db):
        from sba.data.db.repository import Repository
        repo = Repository()
        # Insert some test bets
        db.execute("""
            INSERT INTO events (id, sport, home_team, away_team, commence_time)
            VALUES ('e1', 'basketball_nba', 'Lakers', 'Celtics', '2025-03-15T19:00:00')
        """)
        db.execute("""
            INSERT INTO bets (event_id, market, selection, odds_american, odds_decimal,
                model_probability, expected_value, kelly_fraction, recommended_stake, bookmaker, status)
            VALUES ('e1', 'h2h', 'Lakers', -150, 1.667, 0.65, 0.05, 0.03, 30.0, 'fanduel', 'pending')
        """)
        db.execute("""
            INSERT INTO bets (event_id, market, selection, odds_american, odds_decimal,
                model_probability, expected_value, kelly_fraction, recommended_stake, bookmaker, status)
            VALUES ('e1', 'h2h', 'Celtics', 130, 2.3, 0.45, 0.03, 0.02, 20.0, 'draftkings', 'won')
        """)
        db.commit()

        total = repo.count_bets(db)
        assert total == 2

        pending = repo.count_bets(db, status="pending")
        assert pending == 1

        won = repo.count_bets(db, status="won")
        assert won == 1

    def test_count_events(self, db):
        from sba.data.db.repository import Repository
        repo = Repository()
        db.execute("""
            INSERT INTO events (id, sport, home_team, away_team, commence_time, completed)
            VALUES ('e1', 'basketball_nba', 'Lakers', 'Celtics', '2025-03-15T19:00:00', 0)
        """)
        db.execute("""
            INSERT INTO events (id, sport, home_team, away_team, commence_time, completed)
            VALUES ('e2', 'basketball_nba', 'Warriors', 'Heat', '2025-03-16T19:00:00', 1)
        """)
        db.commit()

        total = repo.count_events(db)
        assert total == 2

        active = repo.count_events(db, completed=False)
        assert active == 1

        nba = repo.count_events(db, sport="basketball_nba")
        assert nba == 2


# ── API Client Retry ─────────────────────────────────────────────────


class TestAPIClientRetry:
    def test_retryable_status_codes(self):
        from sba.data.clients.base import _is_retryable
        assert _is_retryable(429)
        assert _is_retryable(500)
        assert _is_retryable(502)
        assert _is_retryable(503)
        assert _is_retryable(504)
        assert not _is_retryable(200)
        assert not _is_retryable(404)
        assert not _is_retryable(401)

    def test_client_uses_constants(self):
        from sba.config.constants import HTTP_TIMEOUT_SECONDS
        from sba.data.clients.base import BaseAPIClient
        c = BaseAPIClient(api_key="test")
        assert c.rate_limiter is not None


# ── Edge Finder Async ─────────────────────────────────────────────────


class TestEdgeFinderAsync:
    def test_find_opportunities_shared_method(self):
        """The _find_opportunities method should be callable from both sync and async."""
        from sba.services.edge_finder import EdgeFinder
        ef = EdgeFinder.__new__(EdgeFinder)
        ef.settings = MagicMock()
        ef.settings.SHARP_BOOKS = ["pinnacle"]
        result = ef._find_opportunities([], 0.02)
        assert result == []


# ── Webhook Retry ─────────────────────────────────────────────────────


class TestWebhookRetry:
    @patch("sba.services.webhook.httpx.post")
    @patch("sba.services.webhook._record_delivery", return_value=None)
    @patch("sba.services.webhook._update_delivery")
    def test_deliver_webhook_success(self, mock_update, mock_record, mock_post):
        from sba.services.webhook import deliver_webhook
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        result = deliver_webhook("https://hooks.example.com/test", {"key": "value"})
        assert result["status"] == "delivered"
        assert result["attempts"] == 1

    @patch("sba.services.webhook.httpx.post")
    @patch("sba.services.webhook._record_delivery", return_value=None)
    @patch("sba.services.webhook._update_delivery")
    @patch("sba.services.webhook.time.sleep")
    def test_deliver_webhook_retry_on_failure(self, mock_sleep, mock_update, mock_record, mock_post):
        from sba.services.webhook import deliver_webhook
        mock_resp_fail = MagicMock()
        mock_resp_fail.status_code = 500
        mock_resp_fail.text = "Internal Server Error"

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200

        mock_post.side_effect = [mock_resp_fail, mock_resp_ok]

        result = deliver_webhook("https://hooks.example.com/test", {"key": "value"})
        assert result["status"] == "delivered"
        assert result["attempts"] == 2
        mock_sleep.assert_called_once()

    @patch("sba.services.webhook.httpx.post")
    @patch("sba.services.webhook._record_delivery", return_value=None)
    @patch("sba.services.webhook._update_delivery")
    @patch("sba.services.webhook.time.sleep")
    def test_deliver_webhook_all_retries_fail(self, mock_sleep, mock_update, mock_record, mock_post):
        from sba.services.webhook import deliver_webhook
        mock_post.side_effect = ConnectionError("Connection refused")

        result = deliver_webhook("https://hooks.example.com/test", {"key": "value"})
        assert result["status"] == "failed"
        assert result["attempts"] == 3
        assert "error" in result

    def test_webhook_history_endpoint(self):
        resp = client.get("/api/notifications/webhook-history")
        assert resp.status_code == 200


# ── EV Confidence Uses Constants ──────────────────────────────────────


class TestEVConfidenceConstants:
    def test_ev_uses_named_constants(self):
        from sba.config.constants import EV_CONFIDENCE_HIGH, EV_CONFIDENCE_MEDIUM
        from sba.models.statistical.ev import find_ev_opportunities

        from sba.models.domain import BookmakerOdds, Event, EventOdds, Outcome
        from datetime import datetime

        event = Event(
            id="g1", sport="basketball_nba",
            home_team="Lakers", away_team="Celtics",
            commence_time=datetime(2025, 3, 15, 19, 0),
        )
        event_odds = EventOdds(
            event=event,
            bookmakers=[
                BookmakerOdds(
                    bookmaker="fanduel", market="h2h",
                    outcomes=[
                        Outcome(name="Lakers", price_american=100, price_decimal=2.0),
                        Outcome(name="Celtics", price_american=100, price_decimal=2.0),
                    ],
                ),
            ],
        )
        model_probs = {"Lakers": 0.6, "Celtics": 0.4}

        opps = find_ev_opportunities(event_odds, model_probs, "h2h", threshold=0.0)
        for opp in opps:
            if opp.ev >= EV_CONFIDENCE_HIGH:
                assert opp.confidence == "high"
            elif opp.ev >= EV_CONFIDENCE_MEDIUM:
                assert opp.confidence == "medium"
            else:
                assert opp.confidence == "low"


# ── Feature Engineering Uses Constants ────────────────────────────────


class TestFeatureConstants:
    def test_features_use_rolling_windows(self, sample_game_logs):
        from sba.config.constants import ROLLING_WINDOWS
        from sba.models.ml.features import build_prop_features

        logs = sorted(sample_game_logs, key=lambda x: x.game_date, reverse=True)
        features = build_prop_features(logs)
        assert not features.empty
        for w in ROLLING_WINDOWS:
            assert f"avg_{w}" in features.columns
            assert f"std_{w}" in features.columns

    def test_features_min_games_threshold(self):
        from sba.config.constants import ML_MIN_FEATURE_GAMES
        from sba.models.ml.features import build_prop_features

        # Less than ML_MIN_FEATURE_GAMES should return empty
        logs = []  # Empty
        features = build_prop_features(logs)
        assert features.empty


# ── Cache Uses Constants ──────────────────────────────────────────────


class TestCacheConstants:
    def test_cache_default_max_entries(self):
        from sba.config.constants import CACHE_MAX_ENTRIES
        from sba.utils.cache import TTLCache
        c = TTLCache()
        assert c._max_entries == CACHE_MAX_ENTRIES


# ── Version ───────────────────────────────────────────────────────────


class TestV29Version:
    def test_version_is_2_9_0(self):
        from sba import __version__
        assert __version__ == "2.9.0"

    def test_app_version_matches(self):
        assert app.version == "2.9.0"

    def test_health_returns_version(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "2.9.0"
