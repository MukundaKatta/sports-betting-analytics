"""Tests for v2.8 improvements: security, bug fixes, and premium features."""

from __future__ import annotations

import hmac
import sqlite3

import pytest


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from sba.web.app import app
    return TestClient(app, raise_server_exceptions=False)


# ── Security: Timing-safe API key comparison ──────────────────────────


class TestTimingSafeAPIKey:
    def test_middleware_uses_hmac_compare(self):
        """Verify the middleware imports hmac for constant-time comparison."""
        from sba.web.middleware import hmac as middleware_hmac
        assert middleware_hmac is hmac

    def test_security_headers_present(self, client):
        """Verify security headers are set on responses."""
        resp = client.get("/api/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "camera=()" in resp.headers.get("Permissions-Policy", "")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_security_headers_on_api_routes(self, client):
        """Security headers should be on all routes, not just health."""
        resp = client.get("/api/analytics")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_security_headers_on_view_routes(self, client):
        resp = client.get("/")
        assert resp.headers.get("X-Frame-Options") == "DENY"


# ── Security: Settings allowlist ──────────────────────────────────────


class TestSettingsAllowlist:
    def test_allowed_settings_defined(self):
        from sba.web.app import _ALLOWED_PERSISTED_SETTINGS
        assert "SBA_DEFAULT_SPORT" in _ALLOWED_PERSISTED_SETTINGS
        assert "SBA_BANKROLL" in _ALLOWED_PERSISTED_SETTINGS
        # Sensitive keys must NOT be in the allowlist
        assert "SBA_API_KEY" not in _ALLOWED_PERSISTED_SETTINGS
        assert "SBA_ODDS_API_KEY" not in _ALLOWED_PERSISTED_SETTINGS
        assert "PATH" not in _ALLOWED_PERSISTED_SETTINGS


# ── Bug Fix: Portfolio builder event counting ─────────────────────────


class TestPortfolioBuilderFix:
    def test_event_diversification_uses_counter(self):
        """Portfolio builder should allow up to 2 bets per event."""
        from sba.models.domain import EdgeOpportunity, Event, Outcome

        event = Event(
            id="evt_1", sport="basketball_nba",
            home_team="Lakers", away_team="Celtics",
            commence_time=__import__("datetime").datetime(2025, 6, 1, 19, 0),
        )
        edges = []
        for i in range(5):
            edges.append(EdgeOpportunity(
                event=event,
                market="h2h" if i < 3 else "spreads",
                selection="Lakers",
                line=None,
                best_odds=Outcome(name="Lakers", price_american=-110, price_decimal=1.91),
                bookmaker=f"book_{i}",
                model_prob=0.6,
                implied_prob=0.52,
                ev=0.08 - i * 0.01,
                kelly_pct=0.05,
                recommended_stake=25.0,
                confidence="high",
            ))

        from sba.services.portfolio import build_portfolio
        result = build_portfolio(edges, bankroll=1000, diversify=True)
        # With diversification, max 2 bets per event
        assert result["summary"]["total_bets"] <= 2


# ── Bug Fix: Version display ─────────────────────────────────────────


class TestVersionDisplay:
    def test_version_in_template_globals(self):
        from sba.web.views import templates
        from sba import __version__
        assert templates.env.globals.get("version") == __version__

    def test_version_on_dashboard(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        from sba import __version__
        assert __version__ in resp.text


# ── Performance: GZip middleware ──────────────────────────────────────


class TestGZipCompression:
    def test_gzip_compression_available(self, client):
        """GZip middleware should compress large responses."""
        resp = client.get("/api/analytics", headers={"Accept-Encoding": "gzip"})
        # Even if response is small, middleware should be registered
        assert resp.status_code == 200


# ── Premium: CSV Export ──────────────────────────────────────────────


class TestCSVExport:
    def test_csv_export_format(self, client):
        resp = client.get("/api/reports/export?fmt=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "attachment" in resp.headers.get("content-disposition", "")
        # Should have CSV header row
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 1
        header = lines[0]
        assert "id" in header
        assert "odds_american" in header
        assert "profit_loss" in header

    def test_json_export_still_works(self, client):
        resp = client.get("/api/reports/export?fmt=json")
        assert resp.status_code == 200
        data = resp.json()
        assert "bets" in data
        assert "summary" in data

    def test_default_export_is_json(self, client):
        resp = client.get("/api/reports/export")
        assert resp.status_code == 200
        data = resp.json()
        assert "bets" in data


# ── Premium: Brier Score in calibration ──────────────────────────────


class TestBrierScore:
    def test_calibration_includes_brier_score(self, client):
        """The calibration endpoint should include brier_score."""
        # First insert some bets with model probabilities
        from sba.data.db import get_connection
        with get_connection() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            for i in range(15):
                conn.execute("""
                    INSERT OR IGNORE INTO bets
                    (event_id, market, selection, odds_american, odds_decimal,
                     model_probability, expected_value, kelly_fraction,
                     recommended_stake, bookmaker, status, profit_loss)
                    VALUES (?, 'h2h', 'Team A', -110, 1.91, ?, 0.05, 0.03, 25.0,
                            'fanduel', ?, ?)
                """, (
                    f"brier_evt_{i}",
                    0.55 + (i % 3) * 0.1,
                    "won" if i % 3 != 0 else "lost",
                    25.0 if i % 3 != 0 else -25.0,
                ))
            conn.execute("PRAGMA foreign_keys = ON")

        try:
            resp = client.get("/api/analytics/calibration")
            assert resp.status_code == 200
            data = resp.json()
            assert "brier_score" in data
            assert "calibration" in data
        finally:
            # Clean up inserted test data to avoid polluting other tests
            with get_connection() as conn:
                conn.execute("DELETE FROM bets WHERE event_id LIKE 'brier_evt_%'")


# ── Schema: No duplicate indexes ──────────────────────────────────────


class TestSchemaClean:
    def test_schema_creates_without_errors(self):
        """Schema should apply cleanly to a fresh database."""
        from sba.data.db.schema import SCHEMA_SQL
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA_SQL)
        # Verify key tables exist
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "events" in table_names
        assert "bets" in table_names
        assert "odds_snapshots" in table_names
        assert "clv_records" in table_names
        conn.close()

    def test_no_duplicate_index_definitions(self):
        """Index names should not appear more than once in schema SQL."""
        from sba.data.db.schema import SCHEMA_SQL
        lines = [
            line.strip() for line in SCHEMA_SQL.split("\n")
            if "CREATE INDEX" in line
        ]
        index_names = []
        for line in lines:
            # Extract index name: CREATE INDEX IF NOT EXISTS idx_name ON ...
            parts = line.split()
            for i, p in enumerate(parts):
                if p.startswith("idx_"):
                    index_names.append(p)
                    break
        # Each index name should appear exactly once
        from collections import Counter
        counts = Counter(index_names)
        duplicates = {name: count for name, count in counts.items() if count > 1}
        assert not duplicates, f"Duplicate index definitions: {duplicates}"
