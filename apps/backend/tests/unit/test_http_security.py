"""Backend HTTP hardening sözleşme testleri (FP-OPS-003A).

Kapsam:
- `API_TRUSTED_HOSTS` parsing (trim, boş öğe, dedupe, lowercase, wildcard).
- TrustedHost davranışı: izinli host normal yanıt, izinsiz host 400, loopback
  healthcheck host'ları strict ortamda DAİMA izinli.
- Staging/production'da /docs, /redoc, /openapi.json TAMAMEN kapalı (404).
- Temel security header'ları (nosniff / no-referrer / no-store) tüm yanıt
  türlerinde mevcut ve DUPLICATE değil.
- CORS bilinçli olarak YOK: hiçbir yanıt Access-Control-Allow-Origin taşımaz.

Network, Docker, PostgreSQL veya Supabase GEREKTİRMEZ.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.responses import PlainTextResponse

from flowpilot.api.main import create_app
from flowpilot.api.security_headers import SecurityHeadersMiddleware
from flowpilot.config.settings import Settings

_REMOTE_DB = "postgresql+psycopg://flowpilot_app:pw@db.internal.example:5432/flowpilot"
_REMOTE_SUPABASE = "https://project.supabase.co"

_SECURITY_HEADER_EXPECTATIONS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"_env_file": None, "app_environment": "test"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _production_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "app_environment": "production",
        "database_url": SecretStr(_REMOTE_DB),
        "supabase_url": _REMOTE_SUPABASE,
        "api_trusted_hosts": "api.example.test,*.internal.example.test",
    }
    base.update(overrides)
    return _settings(**base)


def _client(settings: Settings) -> TestClient:
    # raise_server_exceptions=False: yanıt HTTP olarak gözlemlenir (middleware yolu).
    return TestClient(create_app(settings=settings), raise_server_exceptions=False)


def _assert_security_headers(response: Any) -> None:
    for name, expected in _SECURITY_HEADER_EXPECTATIONS.items():
        values = response.headers.get_list(name)
        assert values == [expected], f"{name}: {values}"


# ------------------------------------------------------------------- parsing


def test_allowlist_trims_and_drops_empty_items() -> None:
    settings = _settings(api_trusted_hosts="  api.example.test , , ,web.example.test  ")

    assert settings.trusted_host_allowlist == ("api.example.test", "web.example.test")


def test_allowlist_deduplicates_preserving_first_seen_order() -> None:
    settings = _settings(api_trusted_hosts="b.example.test,a.example.test,b.example.test")

    assert settings.trusted_host_allowlist == ("b.example.test", "a.example.test")


def test_allowlist_normalizes_to_lowercase() -> None:
    settings = _settings(api_trusted_hosts="API.Example.TEST,api.example.test")

    assert settings.trusted_host_allowlist == ("api.example.test",)


def test_allowlist_is_empty_for_unset_or_blank() -> None:
    assert _settings().trusted_host_allowlist == ()
    assert _settings(api_trusted_hosts="").trusted_host_allowlist == ()
    assert _settings(api_trusted_hosts="  ,  ").trusted_host_allowlist == ()


def test_allowlist_keeps_subdomain_wildcard_and_bare_wildcard_verbatim() -> None:
    # Parsing yorum yapmaz; bare '*' reddi strict-env doğrulamasındadır.
    settings = _settings(api_trusted_hosts="*.example.test,*")

    assert settings.trusted_host_allowlist == ("*.example.test", "*")


# ----------------------------------------------------- strict-env doğrulaması


def test_production_without_trusted_hosts_fails_fast() -> None:
    with pytest.raises(RuntimeError) as exc:
        create_app(settings=_production_settings(api_trusted_hosts=None))

    assert "API_TRUSTED_HOSTS" in str(exc.value)


def test_staging_with_blank_trusted_hosts_fails_fast() -> None:
    with pytest.raises(RuntimeError) as exc:
        create_app(
            settings=_production_settings(app_environment="staging", api_trusted_hosts="  ,  ")
        )

    assert "API_TRUSTED_HOSTS" in str(exc.value)


def test_bare_wildcard_is_rejected_in_strict_environments() -> None:
    for environment in ("staging", "production"):
        with pytest.raises(RuntimeError) as exc:
            create_app(
                settings=_production_settings(
                    app_environment=environment, api_trusted_hosts="api.example.test,*"
                )
            )
        assert "API_TRUSTED_HOSTS" in str(exc.value)


def test_trusted_hosts_error_does_not_leak_values_or_secrets() -> None:
    with pytest.raises(RuntimeError) as exc:
        create_app(settings=_production_settings(api_trusted_hosts="host-a.gizli.example,*"))

    message = str(exc.value)
    assert "host-a.gizli.example" not in message
    assert _REMOTE_DB not in message


def test_valid_strict_configuration_starts() -> None:
    assert create_app(settings=_production_settings()) is not None


# ------------------------------------------------------------ TrustedHost davranışı


def test_allowed_exact_host_gets_normal_response() -> None:
    client = _client(_production_settings())

    response = client.get("/health/live", headers={"host": "api.example.test"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_allowed_wildcard_subdomain_gets_normal_response() -> None:
    client = _client(_production_settings())

    response = client.get("/health/live", headers={"host": "probe.internal.example.test"})

    assert response.status_code == 200


def test_disallowed_host_gets_400() -> None:
    client = _client(_production_settings())

    response = client.get("/health/live", headers={"host": "evil.example.test"})

    assert response.status_code == 400


def test_loopback_hosts_are_implicitly_allowed_in_strict_env() -> None:
    """Container healthcheck (Host: 127.0.0.1:<port>) strict ortamda ASLA kırılmaz."""
    client = _client(_production_settings())

    for host in ("localhost", "127.0.0.1", "127.0.0.1:8000", "localhost:8000"):
        response = client.get("/health/live", headers={"host": host})
        assert response.status_code == 200, host


def test_bracketed_ipv6_host_is_rejected_fail_closed() -> None:
    """BİLİNEN SINIR: Starlette TrustedHostMiddleware, Host'u naif `split(":")`
    ile ayırdığı için köşeli parantezli IPv6 literal'i (`[::1]:8000`) HİÇBİR
    allowlist kalıbıyla eşleşemez → istek fail-closed 400 alır. Container
    healthcheck IPv4 (127.0.0.1) kullanır ve bundan ETKİLENMEZ
    (docs/operations/http-security.md'de dokümante edilmiştir).
    """
    client = _client(_production_settings())

    response = client.get("/health/live", headers={"host": "[::1]:8000"})

    assert response.status_code == 400
    _assert_security_headers(response)


def test_unset_allowlist_adds_no_middleware_outside_strict_envs() -> None:
    """Mevcut local/test davranışı korunur: her host kabul edilir."""
    for environment in ("local", "test", "development"):
        client = _client(_settings(app_environment=environment))
        response = client.get("/health/live", headers={"host": "anything.example"})
        assert response.status_code == 200, environment


def test_explicit_allowlist_is_enforced_even_outside_strict_envs() -> None:
    client = _client(_settings(api_trusted_hosts="api.example.test"))

    assert client.get("/health/live", headers={"host": "api.example.test"}).status_code == 200
    assert client.get("/health/live", headers={"host": "evil.example.test"}).status_code == 400


# ------------------------------------------------------------------ docs gating


def test_docs_endpoints_are_open_in_test_environment() -> None:
    client = _client(_settings())

    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_endpoints_are_closed_in_strict_environments() -> None:
    for environment in ("staging", "production"):
        client = _client(_production_settings(app_environment=environment))
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = client.get(path, headers={"host": "api.example.test"})
            assert response.status_code == 404, f"{environment} {path}"


# ------------------------------------------------------------- security headers


def test_security_headers_on_success_response() -> None:
    response = _client(_settings()).get("/health/live")

    assert response.status_code == 200
    _assert_security_headers(response)


def test_security_headers_on_readiness_503() -> None:
    # Test ortamında database yapılandırılmamıştır → gerçek 503 yolu.
    response = _client(_settings()).get("/health/ready")

    assert response.status_code == 503
    _assert_security_headers(response)


def test_security_headers_on_404() -> None:
    response = _client(_settings()).get("/boyle-bir-yol-yok")

    assert response.status_code == 404
    _assert_security_headers(response)


def test_security_headers_on_422_validation_error() -> None:
    """Gerçek 422 yolu: fake auth ile geçersiz organizasyon adı (test_api_auth kalıbı)."""
    from datetime import UTC, datetime, timedelta

    from flowpilot.api.deps import (
        get_auth_provider,
        get_create_organization_handler,
        get_ensure_user_handler,
    )
    from flowpilot.modules.identity.application.auth import AuthenticatedIdentity
    from flowpilot.modules.identity.domain.auth_provider import AuthProvider
    from flowpilot.modules.organization.application.commands import (
        CreateOrganizationCommand,
        CreateOrganizationResult,
    )
    from flowpilot.modules.organization.domain.organization_name import OrganizationName
    from tests.unit.fakes import FakeAuthProvider

    app = create_app(settings=_settings())
    identity = AuthenticatedIdentity(
        provider=AuthProvider.SUPABASE,
        provider_subject="sub-actor",
        email="actor@example.com",
        token_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )

    class _FakeEnsureUser:
        def handle(self, _identity: AuthenticatedIdentity) -> object:
            from uuid import UUID

            return UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    class _ValidatingCreateOrganization:
        def handle(self, command: CreateOrganizationCommand) -> CreateOrganizationResult:
            name = OrganizationName(command.organization_name)  # boş ad → 422 yolu
            raise AssertionError(f"beklenmeyen başarı: {name.value}")

    app.dependency_overrides[get_auth_provider] = lambda: FakeAuthProvider({"tok": identity})
    app.dependency_overrides[get_ensure_user_handler] = lambda: _FakeEnsureUser()
    app.dependency_overrides[get_create_organization_handler] = lambda: (
        _ValidatingCreateOrganization()
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/v1/organizations",
        json={"name": "   "},  # geçersiz ad → 422
        headers={"Authorization": "Bearer tok"},
    )

    assert response.status_code == 422
    _assert_security_headers(response)


def test_security_headers_on_trusted_host_400() -> None:
    """TrustedHost reddi de header'ları taşır (middleware sırası sözleşmesi)."""
    client = _client(_production_settings())

    response = client.get("/health/live", headers={"host": "evil.example.test"})

    assert response.status_code == 400
    _assert_security_headers(response)


def test_endpoint_provided_header_value_is_not_duplicated() -> None:
    """Endpoint kendi Cache-Control'ünü koyarsa middleware DOKUNMAZ."""
    app = FastAPI()

    @app.get("/custom")
    def custom() -> PlainTextResponse:
        return PlainTextResponse("ok", headers={"Cache-Control": "no-cache, private"})

    app.add_middleware(SecurityHeadersMiddleware)
    response = TestClient(app).get("/custom")

    assert response.headers.get_list("Cache-Control") == ["no-cache, private"]
    assert response.headers.get_list("X-Content-Type-Options") == ["nosniff"]


# ------------------------------------------------------------------ CORS yokluğu


def test_no_cors_headers_on_any_response() -> None:
    """CORS bilinçli olarak eklenmemiştir: browser API'ye doğrudan gitmez."""
    client = _client(_settings())

    plain = client.get("/health/live", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in plain.headers

    preflight = client.options(
        "/v1/organizations",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    # Permissive preflight cevabı YOKTUR (CORS middleware yok → 405 döner).
    assert "Access-Control-Allow-Origin" not in preflight.headers
    assert preflight.status_code == 405


def test_no_hsts_or_csp_headers_in_this_slice() -> None:
    """HSTS/CSP bu dilimde BİLİNÇLİ olarak yoktur (edge/ayrı dilim kararı)."""
    response = _client(_settings()).get("/health/live")

    assert "Strict-Transport-Security" not in response.headers
    assert "Content-Security-Policy" not in response.headers
    assert "X-Frame-Options" not in response.headers
