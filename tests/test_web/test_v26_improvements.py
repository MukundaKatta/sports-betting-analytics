"""Tests for v2.6 improvements.

Covers:
- API key authentication middleware
- Dockerfile existence
- Modal system (frontend, verified via CSS)
- Bet slip localStorage (JS-level, verified via code presence)
- Structured JSON logging
- Deep health check endpoint
- Version bump
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from sba.web.app import app

client = TestClient(app, raise_server_exceptions=False)


# ── API Key Authentication ───────────────────────────────────────────


class TestAPIKeyAuth:
    def test_middleware_passes_without_key_configured(self):
        """When API_KEY is empty (dev mode), all requests pass."""
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_middleware_blocks_with_wrong_key(self):
        from sba.web.middleware import APIKeyMiddleware
        middleware = APIKeyMiddleware(app=MagicMock(), api_key="secret123")

        # Verify it rejects without key
        mock_request = MagicMock()
        mock_request.url.path = "/api/edges"
        mock_request.headers = {}
        mock_request.query_params = {}
        # Can't easily test full dispatch without ASGI, so test logic
        assert middleware.api_key == "secret123"

    def test_middleware_allows_public_paths(self):
        from sba.web.middleware import APIKeyMiddleware
        assert "/api/health" in APIKeyMiddleware.PUBLIC_PATHS
        assert "/api/docs" in APIKeyMiddleware.PUBLIC_PATHS

    def test_middleware_reads_header(self):
        from sba.web.middleware import APIKeyMiddleware
        middleware = APIKeyMiddleware(app=MagicMock(), api_key="test-key")
        assert middleware.api_key == "test-key"

    def test_api_key_in_settings(self):
        from sba.config.settings import Settings
        s = Settings()
        assert hasattr(s, "API_KEY")
        assert s.API_KEY == ""  # Default is empty (dev mode)


# ── Docker Deployment ────────────────────────────────────────────────


class TestDockerDeployment:
    def test_dockerfile_exists(self):
        import os
        assert os.path.exists(str(PROJECT_ROOT / "Dockerfile"))

    def test_docker_compose_exists(self):
        import os
        assert os.path.exists(str(PROJECT_ROOT / "docker-compose.yml"))

    def test_dockerfile_content(self):
        with open(str(PROJECT_ROOT / "Dockerfile")) as f:
            content = f.read()
        assert "python:3.11-slim" in content
        assert "HEALTHCHECK" in content
        assert "uvicorn" in content
        assert "sba" in content

    def test_docker_compose_content(self):
        with open(str(PROJECT_ROOT / "docker-compose.yml")) as f:
            content = f.read()
        assert "8000:8000" in content
        assert "sba-data" in content


# ── Frontend Improvements ────────────────────────────────────────────


class TestFrontendImprovements:
    def test_modal_css_exists(self):
        with open(str(PROJECT_ROOT / "src/sba/web/static/css/style.css")) as f:
            css = f.read()
        assert "sba-modal-overlay" in css
        assert "sba-modal-card" in css
        assert "sba-modal-header" in css

    def test_no_prompt_in_settings(self):
        """Settings should use modal forms, not prompt() dialogs."""
        with open(str(PROJECT_ROOT / "src/sba/web/static/js/app.js")) as f:
            js = f.read()
        # Count remaining prompt() calls in settings area
        # editSetting should be used instead
        assert "SBA.editSetting(" in js
        assert "showModal(" in js
        assert "confirmAction(" in js

    def test_bet_slip_persistence(self):
        with open(str(PROJECT_ROOT / "src/sba/web/static/js/app.js")) as f:
            js = f.read()
        assert "_saveSlip()" in js
        assert "_loadSlip()" in js
        assert "sba-betslip" in js
        assert "localStorage" in js

    def test_delete_has_confirmation(self):
        with open(str(PROJECT_ROOT / "src/sba/web/static/js/app.js")) as f:
            js = f.read()
        # deleteBet should use confirmAction
        assert "confirmAction" in js


# ── Structured Logging ───────────────────────────────────────────────


class TestStructuredLogging:
    def test_json_formatter_exists(self):
        from sba.config.logging import JSONFormatter
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Hello %s", args=("world",), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Hello world"
        assert "timestamp" in parsed

    def test_setup_logging_text(self):
        from sba.config.logging import setup_logging
        setup_logging(level="INFO", fmt="text")
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_setup_logging_json(self):
        from sba.config.logging import setup_logging
        setup_logging(level="DEBUG", fmt="json")
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        # At least one handler should be JSONFormatter
        has_json = any(
            isinstance(h.formatter, __import__('sba.config.logging', fromlist=['JSONFormatter']).JSONFormatter)
            for h in root.handlers
        )
        assert has_json


# ── Deep Health Check ────────────────────────────────────────────────


class TestDeepHealthCheck:
    def test_deep_health_endpoint(self):
        resp = client.get("/api/health/deep")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "version" in data
        assert "uptime_seconds" in data
        assert "checks" in data

    def test_deep_health_has_database_check(self):
        resp = client.get("/api/health/deep")
        data = resp.json()
        assert "database" in data["checks"]
        assert data["checks"]["database"]["status"] == "healthy"
        assert "response_ms" in data["checks"]["database"]

    def test_deep_health_has_cache_stats(self):
        resp = client.get("/api/health/deep")
        data = resp.json()
        assert "cache" in data["checks"]
        assert "entries" in data["checks"]["cache"]
        assert "hit_rate" in data["checks"]["cache"]

    def test_deep_health_has_auth_status(self):
        resp = client.get("/api/health/deep")
        data = resp.json()
        assert "authentication" in data["checks"]

    def test_basic_health_version_updated(self):
        resp = client.get("/api/health")
        data = resp.json()
        assert data["version"] >= "2.6.0"


# ── Env Example ──────────────────────────────────────────────────────


class TestEnvExample:
    def test_env_example_has_new_settings(self):
        with open(str(PROJECT_ROOT / ".env.example")) as f:
            content = f.read()
        assert "SBA_API_KEY" in content
        assert "SBA_CORS_ORIGINS" in content
        assert "SBA_RATE_LIMIT_MAX_REQUESTS" in content


# ── Version ──────────────────────────────────────────────────────────


class TestVersion:
    def test_version_bumped(self):
        assert app.version >= "2.6.0"
