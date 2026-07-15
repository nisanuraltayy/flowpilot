"""API authentication davranış testleri — fake auth port, DB YOK.

DB gerektiren dependency'ler override edilir; burada yalnız HTTP semantiği
doğrulanır. Gerçek DB akışı integration testlerindedir.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from flowpilot.api.deps import (
    get_auth_provider,
    get_create_organization_handler,
    get_ensure_user_handler,
)
from flowpilot.api.main import create_app
from flowpilot.config.settings import Settings
from flowpilot.modules.identity.application.auth import AuthenticatedIdentity
from flowpilot.modules.identity.domain.auth_provider import AuthProvider
from flowpilot.modules.organization.application.commands import (
    CreateOrganizationCommand,
    CreateOrganizationResult,
)
from flowpilot.modules.organization.domain.organization_name import OrganizationName
from tests.unit.fakes import FakeAuthProvider

ACTOR_UUID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_UUID = UUID("11111111-1111-1111-1111-111111111111")
MEMBERSHIP_UUID = UUID("22222222-2222-2222-2222-222222222222")
VALID_TOKEN = "valid-test-token"
EXPIRED_TOKEN = "expired-test-token"


def _valid_identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider=AuthProvider.SUPABASE,
        provider_subject="sub-actor",
        email="actor@example.com",
        token_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )


class _FakeEnsureUser:
    def handle(self, identity: AuthenticatedIdentity) -> UUID:
        return ACTOR_UUID


class _RecordingCreateOrganization:
    """Handler'a ulaşan command'i kaydeder — actor enjeksiyonu testi için."""

    def __init__(self) -> None:
        self.commands: list[CreateOrganizationCommand] = []

    def handle(self, command: CreateOrganizationCommand) -> CreateOrganizationResult:
        self.commands.append(command)
        # Gerçek handler gibi ad doğrulaması yapar (422 yolu için).
        name = OrganizationName(command.organization_name)
        return CreateOrganizationResult(
            tenant_id=TENANT_UUID,
            owner_membership_id=MEMBERSHIP_UUID,
            organization_name=name.value,
        )


def _app(
    *,
    auth: FakeAuthProvider | None = None,
    handler: _RecordingCreateOrganization | None = None,
) -> tuple[FastAPI, _RecordingCreateOrganization]:
    app = create_app(settings=Settings(_env_file=None, app_environment="test"))
    recording = handler or _RecordingCreateOrganization()
    fake_auth = auth or FakeAuthProvider(
        {VALID_TOKEN: _valid_identity()}, expired_tokens=[EXPIRED_TOKEN]
    )
    app.dependency_overrides[get_auth_provider] = lambda: fake_auth
    app.dependency_overrides[get_ensure_user_handler] = lambda: _FakeEnsureUser()
    app.dependency_overrides[get_create_organization_handler] = lambda: recording
    return app, recording


def _client(**kwargs: object) -> tuple[TestClient, _RecordingCreateOrganization]:
    app, recording = _app(**kwargs)  # type: ignore[arg-type]
    return TestClient(app), recording


# ------------------------------------------------------------------ 401 / 503


def test_missing_token_returns_401_with_www_authenticate() -> None:
    client, _ = _client()
    response = client.post("/v1/organizations", json={"name": "Acme"})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_scheme_returns_401() -> None:
    client, _ = _client()
    response = client.post(
        "/v1/organizations",
        json={"name": "Acme"},
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )

    assert response.status_code == 401


def test_invalid_token_returns_401() -> None:
    client, _ = _client()
    response = client.post(
        "/v1/organizations",
        json={"name": "Acme"},
        headers={"Authorization": "Bearer unknown-token"},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_expired_token_returns_401() -> None:
    client, _ = _client()
    response = client.post(
        "/v1/organizations",
        json={"name": "Acme"},
        headers={"Authorization": f"Bearer {EXPIRED_TOKEN}"},
    )

    assert response.status_code == 401


def test_provider_unavailable_returns_503() -> None:
    client, _ = _client(auth=FakeAuthProvider(unavailable=True))
    response = client.post(
        "/v1/organizations",
        json={"name": "Acme"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    assert response.status_code == 503


def test_unconfigured_supabase_returns_503_not_500() -> None:
    # get_auth_provider override EDILMEZ — settings'te supabase_url yok.
    app = create_app(settings=Settings(_env_file=None, app_environment="test"))
    app.dependency_overrides[get_ensure_user_handler] = lambda: _FakeEnsureUser()
    app.dependency_overrides[get_create_organization_handler] = lambda: (
        _RecordingCreateOrganization()
    )
    client = TestClient(app)

    response = client.post(
        "/v1/organizations",
        json={"name": "Acme"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    assert response.status_code == 503


# ------------------------------------------------------------------ health


def test_health_endpoints_require_no_token() -> None:
    client, _ = _client()
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


# ------------------------------------------------------------------ 201 / 422


def test_valid_token_and_name_returns_201_with_exact_schema() -> None:
    client, _ = _client()
    response = client.post(
        "/v1/organizations",
        json={"name": "Acme Teknoloji"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "organization_id": str(TENANT_UUID),
        "owner_membership_id": str(MEMBERSHIP_UUID),
        "name": "Acme Teknoloji",
    }


def test_invalid_name_returns_422() -> None:
    client, _ = _client()
    response = client.post(
        "/v1/organizations",
        json={"name": "   "},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    assert response.status_code == 422


def test_actor_id_cannot_be_injected_via_body() -> None:
    client, recording = _client()
    attacker_uuid = "99999999-9999-9999-9999-999999999999"

    response = client.post(
        "/v1/organizations",
        json={"name": "Acme", "actor_user_id": attacker_uuid, "user_id": attacker_uuid},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    assert response.status_code == 201
    # Handler'a ulasan actor, TOKEN'dan cozulen kimliktir — body'deki degil.
    assert recording.commands[0].actor_user_id == ACTOR_UUID


def test_response_contains_no_token_or_stack_details() -> None:
    client, _ = _client()
    response = client.post(
        "/v1/organizations",
        json={"name": "Acme"},
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    body = response.text
    assert VALID_TOKEN not in body
    assert "Traceback" not in body


# ------------------------------------------------------------------ OpenAPI


def test_openapi_declares_bearer_security_and_endpoint() -> None:
    client, _ = _client()
    schema = client.get("/openapi.json").json()

    assert "/v1/organizations" in schema["paths"]
    post_op = schema["paths"]["/v1/organizations"]["post"]
    security_schemes = schema["components"]["securitySchemes"]

    bearer_names = [name for name, sch in security_schemes.items() if sch.get("scheme") == "bearer"]
    assert bearer_names, "Bearer security scheme OpenAPI'da yok"
    assert any(bearer_names[0] in req for req in post_op.get("security", []))

    # Health endpoint'leri security GEREKTIRMEZ.
    for path in ("/health/live", "/health/ready"):
        assert "security" not in schema["paths"][path]["get"]
