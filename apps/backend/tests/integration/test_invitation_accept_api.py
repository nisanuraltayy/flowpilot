"""Davet önizleme + kabul API — GERÇEK PostgreSQL (Testcontainers) + fake auth.

Preview auth'suz; accept auth'lu. Response'ta token/token_hash/tam e-posta YOK.
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
from tests.integration.invitation_support import create_tenant_with_owner, force_past_expiry
from tests.unit.fakes import FakeAuthProvider

pytestmark = pytest.mark.integration

INVITEE_EMAIL = "invitee@example.com"

# token -> (provider_subject, email_snapshot)
_TOKEN_IDENTITIES = {
    "tok-owner": ("owner", "owner@example.com"),
    "tok-invitee": ("invitee", INVITEE_EMAIL),
    "tok-other": ("other", "other@example.com"),
    "tok-noemail": ("noemail", None),
}


def _identity(subject: str, email: str | None) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider=AuthProvider.SUPABASE,
        provider_subject=subject,
        email=email,
        token_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(app_sessionmaker: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(settings=Settings(_env_file=None, app_environment="test"))
    fake_auth = FakeAuthProvider(
        {token: _identity(sub, email) for token, (sub, email) in _TOKEN_IDENTITIES.items()}
    )
    app.dependency_overrides[get_auth_provider] = lambda: fake_auth
    app.dependency_overrides[get_session_factory] = lambda: app_sessionmaker
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def org(app_sessionmaker: sessionmaker[Session]) -> dict[str, object]:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    return {"id": tenant_id, "owner": owner_id}


def _create_invitation(
    client: TestClient, org_id: object, *, email: str = INVITEE_EMAIL, role: str = "member"
) -> str:
    resp = client.post(
        f"/v1/organizations/{org_id}/invitations",
        json={"email": email, "role": role},
        headers=_bearer("tok-owner"),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["token"]


# ============================ PREVIEW =======================================


def test_preview_pending_no_auth_minimal_and_no_secrets(
    client: TestClient, org: dict[str, object]
) -> None:
    token = _create_invitation(client, org["id"])
    resp = client.get(f"/v1/invitations/preview?org={org['id']}&token={token}")  # auth YOK
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["organization_id"] == str(org["id"])
    assert body["role"] == "member"
    assert body["status"] == "pending"
    assert "organization_name" in body
    # Güvenlik: token/token_hash ve tam e-posta yok.
    assert "token" not in body and "token_hash" not in body
    assert INVITEE_EMAIL not in resp.text


def test_preview_unknown_token_404(client: TestClient, org: dict[str, object]) -> None:
    resp = client.get(f"/v1/invitations/preview?org={org['id']}&token=nope-nope")
    assert resp.status_code == 404


def test_preview_revoked_404(client: TestClient, org: dict[str, object]) -> None:
    token = _create_invitation(client, org["id"])
    # invitation_id'yi listeden al ve revoke et.
    listing = client.get(f"/v1/organizations/{org['id']}/invitations", headers=_bearer("tok-owner"))
    invitation_id = listing.json()["items"][0]["invitation_id"]
    client.post(
        f"/v1/organizations/{org['id']}/invitations/{invitation_id}/revoke",
        headers=_bearer("tok-owner"),
    )
    resp = client.get(f"/v1/invitations/preview?org={org['id']}&token={token}")
    assert resp.status_code == 404


def test_preview_expired_410(
    client: TestClient, org: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    token = _create_invitation(client, org["id"])
    listing = client.get(f"/v1/organizations/{org['id']}/invitations", headers=_bearer("tok-owner"))
    invitation_id = listing.json()["items"][0]["invitation_id"]
    force_past_expiry(app_sessionmaker, tenant_id=org["id"], invitation_id=invitation_id)  # type: ignore[arg-type]
    resp = client.get(f"/v1/invitations/preview?org={org['id']}&token={token}")
    assert resp.status_code == 410


def test_preview_cross_tenant_404(
    client: TestClient, org: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    token = _create_invitation(client, org["id"])
    tenant_b, _ = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-b")
    resp = client.get(f"/v1/invitations/preview?org={tenant_b}&token={token}")
    assert resp.status_code == 404


# ============================ ACCEPT ========================================


def _accept(client: TestClient, org_id: object, token: str, who: str) -> object:
    return client.post(
        "/v1/invitations/accept",
        json={"organization_id": str(org_id), "token": token},
        headers=_bearer(who),
    )


def test_accept_happy_creates_membership(client: TestClient, org: dict[str, object]) -> None:
    token = _create_invitation(client, org["id"])
    resp = _accept(client, org["id"], token, "tok-invitee")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["duplicate"] is False
    assert body["role"] == "member"
    assert body["status"] == "active"
    assert "token" not in body and "token_hash" not in body


def test_accept_admin_invite_creates_admin_membership(
    client: TestClient, org: dict[str, object]
) -> None:
    token = _create_invitation(client, org["id"], role="admin")
    resp = _accept(client, org["id"], token, "tok-invitee")
    assert resp.status_code == 200 and resp.json()["role"] == "admin"


def test_accept_requires_auth(client: TestClient, org: dict[str, object]) -> None:
    token = _create_invitation(client, org["id"])
    resp = client.post(
        "/v1/invitations/accept", json={"organization_id": str(org["id"]), "token": token}
    )
    assert resp.status_code == 401


def test_accept_wrong_email_403(client: TestClient, org: dict[str, object]) -> None:
    token = _create_invitation(client, org["id"])
    resp = _accept(client, org["id"], token, "tok-other")  # other@example.com
    assert resp.status_code == 403


def test_accept_missing_email_snapshot_403(client: TestClient, org: dict[str, object]) -> None:
    token = _create_invitation(client, org["id"])
    resp = _accept(client, org["id"], token, "tok-noemail")  # email_snapshot None
    assert resp.status_code == 403


def test_accept_unknown_token_404(client: TestClient, org: dict[str, object]) -> None:
    resp = _accept(client, org["id"], "nope-token", "tok-invitee")
    assert resp.status_code == 404


def test_accept_revoked_404(client: TestClient, org: dict[str, object]) -> None:
    token = _create_invitation(client, org["id"])
    listing = client.get(f"/v1/organizations/{org['id']}/invitations", headers=_bearer("tok-owner"))
    invitation_id = listing.json()["items"][0]["invitation_id"]
    client.post(
        f"/v1/organizations/{org['id']}/invitations/{invitation_id}/revoke",
        headers=_bearer("tok-owner"),
    )
    resp = _accept(client, org["id"], token, "tok-invitee")
    assert resp.status_code == 404


def test_accept_expired_410(
    client: TestClient, org: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    token = _create_invitation(client, org["id"])
    listing = client.get(f"/v1/organizations/{org['id']}/invitations", headers=_bearer("tok-owner"))
    invitation_id = listing.json()["items"][0]["invitation_id"]
    force_past_expiry(app_sessionmaker, tenant_id=org["id"], invitation_id=invitation_id)  # type: ignore[arg-type]
    resp = _accept(client, org["id"], token, "tok-invitee")
    assert resp.status_code == 410


def test_accept_cross_tenant_404(
    client: TestClient, org: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    token = _create_invitation(client, org["id"])
    tenant_b, _ = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-b")
    resp = _accept(client, tenant_b, token, "tok-invitee")
    assert resp.status_code == 404


def test_accept_replay_is_duplicate(client: TestClient, org: dict[str, object]) -> None:
    token = _create_invitation(client, org["id"])
    first = _accept(client, org["id"], token, "tok-invitee")
    second = _accept(client, org["id"], token, "tok-invitee")
    assert first.status_code == 200 and first.json()["duplicate"] is False
    assert second.status_code == 200 and second.json()["duplicate"] is True
    assert second.json()["membership_id"] == first.json()["membership_id"]


def test_accept_accepted_by_other_user_404(client: TestClient, org: dict[str, object]) -> None:
    token = _create_invitation(client, org["id"])
    _accept(client, org["id"], token, "tok-invitee")  # invitee kabul etti
    # Başka authenticated kullanıcı aynı accepted token'ı kullanamaz → 404 (sızdırmaz).
    resp = _accept(client, org["id"], token, "tok-other")
    assert resp.status_code == 404


def test_accept_invalid_body_422(client: TestClient, org: dict[str, object]) -> None:
    # Eksik token alanı → 422.
    resp = client.post(
        "/v1/invitations/accept",
        json={"organization_id": str(org["id"])},
        headers=_bearer("tok-invitee"),
    )
    assert resp.status_code == 422
    # Geçersiz UUID → 422.
    resp2 = client.post(
        "/v1/invitations/accept",
        json={"organization_id": "not-a-uuid", "token": "x"},
        headers=_bearer("tok-invitee"),
    )
    assert resp2.status_code == 422
