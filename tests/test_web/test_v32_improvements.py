"""Tests for v3.2 improvements.

Covers:
- Signal rating system (traffic light + confidence)
- Smart Signals page and API enhancements
- Version alignment (3.2.0)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sba.web.app import app

client = TestClient(app, raise_server_exceptions=False)


# ── Signal Rating Service ──────────────────────────────────────


class TestSignalRating:
    def test_high_edge_green_signal(self):
        """High edge should produce green signal."""
        from sba.services.signal_rating import rate_opportunity
        rating = rate_opportunity(edge_pct=8.0, sharp_agrees=True)
        assert rating.signal == "green"
        assert rating.confidence >= 50
        assert rating.stars >= 4
        assert rating.label == "Strong Play"

    def test_moderate_edge_yellow_signal(self):
        """Moderate edge without confirmation should be yellow."""
        from sba.services.signal_rating import rate_opportunity
        rating = rate_opportunity(edge_pct=3.0)
        assert rating.signal in ("green", "yellow")
        assert rating.stars >= 2

    def test_no_edge_red_signal(self):
        """No edge should produce red signal."""
        from sba.services.signal_rating import rate_opportunity
        rating = rate_opportunity(edge_pct=0.0)
        assert rating.signal == "red"
        assert rating.confidence < 40
        assert rating.label == "Avoid"

    def test_sharp_agreement_boosts_confidence(self):
        """Sharp agreement should boost confidence."""
        from sba.services.signal_rating import rate_opportunity
        without = rate_opportunity(edge_pct=4.0)
        with_sharp = rate_opportunity(edge_pct=4.0, sharp_agrees=True)
        assert with_sharp.confidence > without.confidence

    def test_line_movement_toward_boosts(self):
        """Confirming line movement should boost."""
        from sba.services.signal_rating import rate_opportunity
        base = rate_opportunity(edge_pct=4.0)
        with_move = rate_opportunity(edge_pct=4.0, line_moving_toward=True)
        assert with_move.confidence > base.confidence

    def test_line_movement_away_penalizes(self):
        """Line moving away should penalize."""
        from sba.services.signal_rating import rate_opportunity
        base = rate_opportunity(edge_pct=4.0, sharp_agrees=True)
        with_away = rate_opportunity(edge_pct=4.0, sharp_agrees=False, line_moving_away=True)
        assert with_away.confidence < base.confidence

    def test_pattern_match_boosts(self):
        """Pattern match should boost confidence."""
        from sba.services.signal_rating import rate_opportunity
        base = rate_opportunity(edge_pct=4.0)
        with_pattern = rate_opportunity(edge_pct=4.0, pattern_confidence=80, pattern_roi=15)
        assert with_pattern.confidence > base.confidence

    def test_ml_probability_boosts(self):
        """ML probability > 0.5 should boost."""
        from sba.services.signal_rating import rate_opportunity
        base = rate_opportunity(edge_pct=4.0)
        with_ml = rate_opportunity(edge_pct=4.0, ml_probability=0.7)
        assert with_ml.confidence > base.confidence

    def test_live_market_penalty(self):
        """Live markets should have reduced confidence."""
        from sba.services.signal_rating import rate_opportunity
        pre = rate_opportunity(edge_pct=5.0, sharp_agrees=True)
        live = rate_opportunity(edge_pct=5.0, sharp_agrees=True, is_live=True)
        assert live.confidence < pre.confidence

    def test_reasons_populated(self):
        """Should have at least one reason."""
        from sba.services.signal_rating import rate_opportunity
        rating = rate_opportunity(edge_pct=5.0, sharp_agrees=True)
        assert len(rating.reasons) > 0

    def test_warnings_on_stale_line(self):
        """Single-book edge in multi-book market should warn."""
        from sba.services.signal_rating import rate_opportunity
        rating = rate_opportunity(edge_pct=3.0, books_with_edge=1, total_books=8)
        assert any("1 book" in w for w in rating.warnings)

    def test_star_range(self):
        """Stars should be 1-5."""
        from sba.services.signal_rating import rate_opportunity
        for edge in [0, 2, 4, 6, 10]:
            rating = rate_opportunity(edge_pct=edge, sharp_agrees=edge > 5)
            assert 1 <= rating.stars <= 5


# ── Signal Rating API ──────────────────────────────────────────


class TestSignalRatingAPI:
    def test_rate_endpoint(self):
        """POST /api/signals/rate should return 200."""
        resp = client.post("/api/signals/rate", params={"edge_pct": 5.0, "sharp_agrees": True})
        assert resp.status_code == 200
        data = resp.json()
        assert "signal" in data
        assert data["signal"] in ("green", "yellow", "red")
        assert "confidence" in data
        assert "stars" in data
        assert "label" in data
        assert "reasons" in data
        assert "warnings" in data

    def test_rate_with_all_params(self):
        """Rate with all parameters provided."""
        resp = client.post("/api/signals/rate", params={
            "ev_pct": 0.05,
            "edge_pct": 5.0,
            "sharp_agrees": True,
            "line_moving_toward": True,
            "pattern_confidence": 75.0,
            "ml_probability": 0.65,
            "books_with_edge": 3,
            "total_books": 8,
            "odds_american": -110,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["signal"] == "green"
        assert data["confidence"] >= 50

    def test_rate_minimal_params(self):
        """Rate with only default params should work."""
        resp = client.post("/api/signals/rate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["signal"] == "red"


# ── Smart Signals Pages ────────────────────────────────────────


class TestSmartSignalsPages:
    def test_smart_signals_page_loads(self):
        """Smart signals page should load."""
        resp = client.get("/smart-signals")
        assert resp.status_code == 200
        assert "Smart Signals" in resp.text

    def test_signals_api_endpoint(self):
        """GET /api/signals should return 200."""
        resp = client.get("/api/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert "patterns_found" in data
        assert "active_signals" in data

    def test_patterns_api_endpoint(self):
        """GET /api/signals/patterns should return 200."""
        resp = client.get("/api/signals/patterns")
        assert resp.status_code == 200


# ── Version Alignment ──────────────────────────────────────────


class TestVersionAlignment:
    def test_version_is_3_2_plus(self):
        """__version__ should be at least 3.2.0."""
        from sba import __version__
        assert __version__ >= "3.2.0"

    def test_app_version_matches(self):
        """FastAPI app.version should match __version__."""
        from sba import __version__
        assert app.version == __version__

    def test_health_version(self):
        """Health endpoint should report current version."""
        from sba import __version__
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["version"] == __version__
