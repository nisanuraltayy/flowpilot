"""Health endpoint testleri.

Network, Docker, PostgreSQL veya Supabase GEREKTİRMEZ. Readiness'in "hazır" yolu
sahte (in-memory) bir session factory ile doğrulanır; gerçek database açılmaz.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from flowpilot.api.main import create_app
from flowpilot.config.settings import Settings

_SECRET_DSN = "postgresql+psycopg://flowpilot_app:s3cr3t-pw@db.internal.example:5432/flowpilot"


def _app() -> FastAPI:
    """Ayarlar enjekte edilir — global duruma dokunulmaz.

    `_env_file=None` ZORUNLU: aksi hâlde repo kökündeki geliştirici `.env` dosyası
    okunur ve testler "local DATABASE_URL var mı / local Postgres ayakta mı"ya
    bağımlı hâle gelir (CI'da .env yoktur → farklı sonuç). Hermetik kalmalı.
    """
    return create_app(settings=Settings(_env_file=None, app_environment="test"))


def _client() -> TestClient:
    return TestClient(_app())


# --------------------------------------------------------------- sahte session factory


class _FakeSession:
    """`with factory() as session: session.execute(...)` sözleşmesini taklit eder."""

    def __init__(self, *, fail: bool) -> None:
        self._fail = fail
        self.executed = 0

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, statement: Any) -> None:
        self.executed += 1
        if self._fail:
            # Gerçek driver hatası gibi: mesajı DSN/parola içerir.
            raise RuntimeError(f"could not connect to {_SECRET_DSN}")


class _FakeSessionFactory:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.calls = 0

    def __call__(self) -> _FakeSession:
        self.calls += 1
        return _FakeSession(fail=self._fail)


def _client_with_database(*, fail: bool = False) -> tuple[TestClient, _FakeSessionFactory]:
    app = _app()
    factory = _FakeSessionFactory(fail=fail)
    # Paylaşılan (cache'lenmiş) session factory — readiness bunu YENİDEN KULLANIR.
    app.state.session_factory = factory
    return TestClient(app), factory


# ------------------------------------------------------------------------ temel


def test_create_app_returns_fastapi_instance() -> None:
    assert isinstance(_app(), FastAPI)


def test_liveness_returns_exactly_status_ok() -> None:
    """Liveness sözleşmesi DEĞİŞMEDİ — hiçbir bağımlılık kontrol edilmez."""
    response = _client().get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_is_ok_even_when_database_is_unavailable() -> None:
    client, _ = _client_with_database(fail=True)

    assert client.get("/health/live").status_code == 200


# -------------------------------------------------------------------- readiness


def test_readiness_reports_database_ok_when_connection_succeeds() -> None:
    client, factory = _client_with_database()

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": {"status": "ok"}}}
    assert factory.calls == 1  # gerçek bir bağlantı sorgusu yapıldı


def test_readiness_returns_503_when_database_query_fails() -> None:
    client, _ = _client_with_database(fail=True)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"database": {"status": "failed"}}}


def test_readiness_returns_503_when_database_is_not_configured() -> None:
    """DATABASE_URL yoksa readiness sessizce 'ready' DEMEZ."""
    response = _client().get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"database": {"status": "failed"}}}


def test_readiness_failure_never_leaks_connection_details() -> None:
    """Ham driver hatası / DSN / parola response gövdesine TAŞINMAZ."""
    client, _ = _client_with_database(fail=True)

    body = client.get("/health/ready").text

    assert _SECRET_DSN not in body
    assert "s3cr3t-pw" not in body
    assert "db.internal.example" not in body
    assert "could not connect" not in body
    assert "Traceback" not in body


def test_readiness_reuses_shared_session_factory_across_requests() -> None:
    """Her istekte YENİ engine kurulmaz; paylaşılan factory yeniden kullanılır."""
    client, factory = _client_with_database()
    app_factory_before = client.app.state.session_factory  # type: ignore[attr-defined]

    for _ in range(3):
        assert client.get("/health/ready").status_code == 200

    assert factory.calls == 3
    assert client.app.state.session_factory is app_factory_before  # type: ignore[attr-defined]


def test_readiness_does_not_crash_process_on_database_failure() -> None:
    """Bağlantı hatası exception olarak DIŞARI SIZMAZ (probe süreci çökertmez)."""
    client, _ = _client_with_database(fail=True)

    # İstek exception fırlatmadan tamamlanır ve sonraki istekler çalışmaya devam eder.
    assert client.get("/health/ready").status_code == 503
    assert client.get("/health/live").status_code == 200


# ------------------------------------------------------------------ auth / import


@pytest.mark.parametrize(
    ("path", "expected_status"),
    [("/health/live", 200), ("/health/ready", 503)],
)
def test_health_endpoints_require_no_authentication(path: str, expected_status: int) -> None:
    # Authorization header GÖNDERİLMEDEN cevap döner; 401/403 OLMAZ.
    response = _client().get(path)

    assert response.status_code == expected_status
    assert response.status_code not in (401, 403)
    assert "WWW-Authenticate" not in response.headers


def test_app_import_does_not_open_database_or_provider_connection() -> None:
    # Uygulama nesnesi kurulurken hiçbir dış bağlantı kurulmaz:
    # state'te yalnız settings bulunur, engine/client bulunmaz.
    app = _app()

    state = vars(app.state)["_state"]
    assert set(state) == {"settings"}
