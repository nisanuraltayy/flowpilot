"""Purchase Request HTTP API — GERÇEK PostgreSQL + fake auth (uçtan uca).

Token/e-posta/secret test çıktısında görünmez. Gerçek Supabase ağına çağrı YOK.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.api.deps import get_auth_provider, get_session_factory
from flowpilot.api.main import create_app
from flowpilot.config.settings import Settings
from flowpilot.modules.identity.application.auth import AuthenticatedIdentity
from flowpilot.modules.identity.domain.auth_provider import AuthProvider
from tests.unit.fakes import FakeAuthProvider

pytestmark = pytest.mark.integration

TOKEN_A = "pr-token-a"
TOKEN_B = "pr-token-b"


def _identity(subject: str) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider=AuthProvider.SUPABASE,
        provider_subject=subject,
        email=f"{subject}@example.com",
        token_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )


@pytest.fixture
def client(app_sessionmaker: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(settings=Settings(_env_file=None, app_environment="test"))
    fake_auth = FakeAuthProvider({TOKEN_A: _identity("pr-sub-a"), TOKEN_B: _identity("pr-sub-b")})
    app.dependency_overrides[get_auth_provider] = lambda: fake_auth
    app.dependency_overrides[get_session_factory] = lambda: app_sessionmaker
    with TestClient(app) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_org(client: TestClient, token: str, name: str = "Acme") -> str:
    resp = client.post("/v1/organizations", json={"name": name}, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    return str(resp.json()["organization_id"])


def test_post_purchase_request_returns_201_and_starts_workflow(client: TestClient) -> None:
    org_id = _create_org(client, TOKEN_A)
    resp = client.post(
        f"/v1/organizations/{org_id}/purchase-requests",
        json={
            "title": "Yeni dizüstü bilgisayar alımı",
            "description": "Yazılım ekibi için",
            "amount_minor": 1_250_000,
            "currency": "TRY",
        },
        headers=_auth(TOKEN_A),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["organization_id"] == org_id
    assert body["status"] == "in_approval"
    assert body["amount_minor"] == 1_250_000
    assert body["currency"] == "TRY"
    # 1.250.000 kuruş = 12.500 TL → 10k-50k bandı → ilk adım team_manager.
    assert body["current_approval_role"] == "team_manager"
    assert body["workflow_instance_id"]
    assert body["created_at"]


def test_get_purchase_request_returns_detail(client: TestClient) -> None:
    org_id = _create_org(client, TOKEN_A)
    created = client.post(
        f"/v1/organizations/{org_id}/purchase-requests",
        json={"title": "Sunucu", "amount_minor": 6_000_000, "currency": "TRY"},
        headers=_auth(TOKEN_A),
    ).json()
    pr_id = created["purchase_request_id"]

    resp = client.get(
        f"/v1/organizations/{org_id}/purchase-requests/{pr_id}", headers=_auth(TOKEN_A)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purchase_request_id"] == pr_id
    assert body["requested_by_current_user"] is True
    assert body["status"] == "in_approval"
    assert body["workflow_status"] == "waiting"
    # 60.000 TL → >50k bandı → ilk adım team_manager (3'lü zincir).
    assert body["current_approval_role"] == "team_manager"


def test_missing_auth_returns_401(client: TestClient) -> None:
    org_id = _create_org(client, TOKEN_A)
    resp = client.post(
        f"/v1/organizations/{org_id}/purchase-requests",
        json={"title": "x", "amount_minor": 1000, "currency": "TRY"},
    )
    assert resp.status_code == 401


def test_invalid_amount_returns_422(client: TestClient) -> None:
    org_id = _create_org(client, TOKEN_A)
    resp = client.post(
        f"/v1/organizations/{org_id}/purchase-requests",
        json={"title": "x", "amount_minor": 0, "currency": "TRY"},
        headers=_auth(TOKEN_A),
    )
    assert resp.status_code == 422


def test_non_currency_try_returns_422(client: TestClient) -> None:
    org_id = _create_org(client, TOKEN_A)
    resp = client.post(
        f"/v1/organizations/{org_id}/purchase-requests",
        json={"title": "x", "amount_minor": 1000, "currency": "USD"},
        headers=_auth(TOKEN_A),
    )
    assert resp.status_code == 422


def test_non_member_cannot_create_in_other_org(client: TestClient) -> None:
    org_a = _create_org(client, TOKEN_A, name="A org")
    _create_org(client, TOKEN_B, name="B org")  # B kendi org'unu kurar
    # Token B, A'nın org'unda talep oluşturamaz → üyelik yok → 404 (varlık sızmaz).
    resp = client.post(
        f"/v1/organizations/{org_a}/purchase-requests",
        json={"title": "x", "amount_minor": 1000, "currency": "TRY"},
        headers=_auth(TOKEN_B),
    )
    assert resp.status_code == 404


def test_cross_tenant_get_is_not_found(client: TestClient) -> None:
    org_a = _create_org(client, TOKEN_A, name="A org")
    org_b = _create_org(client, TOKEN_B, name="B org")
    created = client.post(
        f"/v1/organizations/{org_a}/purchase-requests",
        json={"title": "gizli", "amount_minor": 1000, "currency": "TRY"},
        headers=_auth(TOKEN_A),
    ).json()
    pr_id = created["purchase_request_id"]

    # Token B, kendi org'u üzerinden A'nın PR id'sini sorgular → 404.
    resp = client.get(
        f"/v1/organizations/{org_b}/purchase-requests/{pr_id}", headers=_auth(TOKEN_B)
    )
    assert resp.status_code == 404
