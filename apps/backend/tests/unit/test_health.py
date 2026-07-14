"""Health endpoint testleri.

Network, Docker, PostgreSQL veya Supabase GEREKTİRMEZ.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from flowpilot.api.main import create_app
from flowpilot.config.settings import Settings


def _client() -> TestClient:
    # Ayarlar enjekte edilir — global duruma dokunulmaz.
    app = create_app(settings=Settings(app_environment="test"))
    return TestClient(app)


def test_create_app_returns_fastapi_instance() -> None:
    app = create_app(settings=Settings(app_environment="test"))
    assert isinstance(app, FastAPI)


def test_liveness_returns_exactly_status_ok() -> None:
    response = _client().get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_exactly_ready_with_empty_checks() -> None:
    response = _client().get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {}}


def test_health_endpoints_require_no_authentication() -> None:
    # Authorization header GÖNDERİLMEDEN 200 dönmeli; 401/403 olmamalı.
    client = _client()

    for path in ("/health/live", "/health/ready"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "WWW-Authenticate" not in response.headers, path


def test_app_import_does_not_open_database_or_provider_connection() -> None:
    # Uygulama nesnesi kurulurken hiçbir dış bağlantı kurulmaz:
    # state'te yalnız settings bulunur, engine/client bulunmaz.
    app = create_app(settings=Settings(app_environment="test"))

    state = vars(app.state)["_state"]
    assert set(state) == {"settings"}
