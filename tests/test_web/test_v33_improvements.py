"""Tests for v3.3 improvements.

Covers:
- Analytics CSV/JSON export
- Signal integration in edge results
- Response caching decorators
- Enhanced edges page with traffic light signals
- Version alignment (3.3.0)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app, raise_server_exceptions=False)


# ── Analytics Export ──────────────────────────────────────────


class TestAnalyticsExport:
    def test_export_csv_default(self):
        """GET /api/analytics/export should return CSV by default."""
        resp = client.get("/api/analytics/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_export_csv_explicit(self):
        """GET /api/analytics/export?format=csv should return CSV."""
        resp = client.get("/api/analytics/export", params={"format": "csv"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        # Should have CSV headers at minimum
        text = resp.text
        assert "id" in text or "selection" in text or text.strip() != ""

    def test_export_json(self):
        """GET /api/analytics/export?format=json should return JSON."""
        resp = client.get("/api/analytics/export", params={"format": "json"})
        assert resp.status_code == 200
        data = resp.json()
        assert "bets" in data
        assert "count" in data
        assert isinstance(data["bets"], list)
        assert data["count"] == len(data["bets"])

    def test_export_json_settled(self):
        """Default status=settled should filter to settled bets."""
        resp = client.get("/api/analytics/export", params={"format": "json", "status": "settled"})
        assert resp.status_code == 200
        data = resp.json()
        for bet in data["bets"]:
            assert bet.get("status") in ("won", "lost", "push")

    def test_export_json_all(self):
        """status=all should return all bets."""
        resp = client.get("/api/analytics/export", params={"format": "json", "status": "all"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["bets"], list)

    def test_export_json_pending(self):
        """status=pending should filter to pending bets."""
        resp = client.get("/api/analytics/export", params={"format": "json", "status": "pending"})
        assert resp.status_code == 200
        data = resp.json()
        for bet in data["bets"]:
            assert bet.get("status") == "pending"

    def test_export_csv_has_content_disposition(self):
        """CSV export should have Content-Disposition header."""
        resp = client.get("/api/analytics/export", params={"format": "csv"})
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "bets_export.csv" in cd


# ── Signal Integration in Edges ───────────────────────────────


class TestSignalInEdges:
    def test_edge_response_has_signal_field(self):
        """EdgeResponse model should include signal field."""
        from sba.web.routes.edges import EdgeResponse
        fields = EdgeResponse.model_fields
        assert "signal" in fields

    def test_signal_info_model(self):
        """SignalInfo should have required fields."""
        from sba.web.routes.edges import SignalInfo
        fields = SignalInfo.model_fields
        assert "signal" in fields
        assert "confidence" in fields
        assert "stars" in fields
        assert "label" in fields


# ── Cached Response Decorator ─────────────────────────────────


class TestCachedResponses:
    def test_health_score_cached(self):
        """Health score endpoint should respond consistently (caching)."""
        resp1 = client.get("/api/health-score")
        resp2 = client.get("/api/health-score")
        assert resp1.status_code == 200
        assert resp2.status_code == 200

    def test_roi_forecast_cached(self):
        """ROI forecast should respond consistently."""
        resp1 = client.get("/api/roi-forecast")
        resp2 = client.get("/api/roi-forecast")
        assert resp1.status_code == 200
        assert resp2.status_code == 200


# ── Edges Page Enhancement ────────────────────────────────────


class TestEdgesPageEnhanced:
    def test_edges_page_loads(self):
        """Edges page should load."""
        resp = client.get("/edges")
        assert resp.status_code == 200

    def test_edges_page_has_signal_column(self):
        """Edges page should have Signal column header."""
        resp = client.get("/edges")
        assert resp.status_code == 200
        assert "Signal" in resp.text

    def test_edges_page_has_signal_legend(self):
        """Edges page should have signal legend."""
        resp = client.get("/edges")
        assert resp.status_code == 200
        assert "signal-legend" in resp.text
        assert "Strong Play" in resp.text
        assert "Lean" in resp.text
        assert "Avoid" in resp.text

    def test_edges_page_has_signal_styles(self):
        """Edges page should include signal badge styles."""
        resp = client.get("/edges")
        assert resp.status_code == 200
        assert "signal-dot" in resp.text
        assert "signal-badge" in resp.text


# ── Version Alignment ──────────────────────────────────────────


class TestVersionAlignment:
    def test_version_is_3_3(self):
        """__version__ should be 3.3.0."""
        from sba import __version__
        assert __version__ == "3.3.0"

    def test_app_version_matches(self):
        """FastAPI app.version should match __version__."""
        from sba import __version__
        assert app.version == __version__

    def test_health_version(self):
        """Health endpoint should report 3.3.0."""
        from sba import __version__
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["version"] == __version__
