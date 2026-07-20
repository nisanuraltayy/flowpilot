"""Invitation API — GERÇEK PostgreSQL (Testcontainers) + fake auth.

HTTP akışı + RLS + güvenlik uçtan uca doğrulanır. Gerçek Supabase ağına ÇAĞRI YOK.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.api.deps import get_auth_provider, get_session_factory
from flowpilot.api.main import create_app
from flowpilot.config.settings import Settings
from tests.integration.invitation_support import (
    add_member,
    create_tenant_with_owner,
    identity_for,
    invitation_rows,
)
from tests.unit.fakes import FakeAuthProvider

pytestmark = pytest.mark.integration

FRONTEND_BASE = "https://app.test"

TOKENS = {
    "owner": "tok-owner",
    "admin": "tok-admin",
    "member": "tok-member",
    "stranger": "tok-stranger",
    "owner_b": "tok-owner-b",
}


def _auth_headers(who: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[who]}", **extra}


@pytest.fixture
def client(app_sessionmaker: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(
        settings=Settings(_env_file=None, app_environment="test", frontend_base_url=FRONTEND_BASE)
    )
    fake_auth = FakeAuthProvider({token: identity_for(name) for name, token in TOKENS.items()})
    app.dependency_overrides[get_auth_provider] = lambda: fake_auth
    app.dependency_overrides[get_session_factory] = lambda: app_sessionmaker
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def tenant(app_sessionmaker: sessionmaker[Session]) -> dict[str, object]:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    admin_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="admin", role="admin")
    member_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="member", role="member")
    return {"id": tenant_id, "owner": owner_id, "admin": admin_id, "member": member_id}


def _invites_url(tenant_id: object) -> str:
    return f"/v1/organizations/{tenant_id}/invitations"


# --- create ------------------------------------------------------------------


def test_owner_creates_invitation_and_token_returned_once(
    client: TestClient, tenant: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    response = client.post(
        _invites_url(tenant["id"]),
        json={"email": "  New.Person@Example.COM ", "role": "member"},
        headers=_auth_headers("owner"),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["invited_email"] == "new.person@example.com"  # normalize
    assert body["role"] == "member"
    assert body["status"] == "pending"
    assert body["duplicate"] is False
    assert body["token"]  # ham token bir kez döner
    assert body["accept_url"].startswith(f"{FRONTEND_BASE}/invitations/accept?org={tenant['id']}")
    assert body["token"] in body["accept_url"]
    assert "token_hash" not in body

    rows = invitation_rows(app_sessionmaker, tenant["id"])  # type: ignore[arg-type]
    assert len(rows) == 1
    stored = rows[0]
    # DB'de YALNIZ hash var; ham token HİÇBİR kolonda görünmez.
    assert stored["token_hash"] == hashlib.sha256(body["token"].encode()).hexdigest()
    assert body["token"] not in str(stored)


def test_admin_can_create(client: TestClient, tenant: dict[str, object]) -> None:
    response = client.post(
        _invites_url(tenant["id"]),
        json={"email": "someone@example.com", "role": "admin"},
        headers=_auth_headers("admin"),
    )
    assert response.status_code == 201, response.text


def test_member_forbidden(client: TestClient, tenant: dict[str, object]) -> None:
    response = client.post(
        _invites_url(tenant["id"]),
        json={"email": "someone@example.com", "role": "member"},
        headers=_auth_headers("member"),
    )
    assert response.status_code == 403


def test_non_member_not_found(client: TestClient, tenant: dict[str, object]) -> None:
    response = client.post(
        _invites_url(tenant["id"]),
        json={"email": "someone@example.com", "role": "member"},
        headers=_auth_headers("stranger"),
    )
    assert response.status_code == 404


def test_missing_token_unauthorized(client: TestClient, tenant: dict[str, object]) -> None:
    response = client.post(
        _invites_url(tenant["id"]), json={"email": "x@example.com", "role": "member"}
    )
    assert response.status_code == 401


def test_invalid_email_returns_422(client: TestClient, tenant: dict[str, object]) -> None:
    response = client.post(
        _invites_url(tenant["id"]),
        json={"email": "not-an-email", "role": "member"},
        headers=_auth_headers("owner"),
    )
    assert response.status_code == 422


def test_owner_role_invite_rejected_422(client: TestClient, tenant: dict[str, object]) -> None:
    response = client.post(
        _invites_url(tenant["id"]),
        json={"email": "x@example.com", "role": "owner"},
        headers=_auth_headers("owner"),
    )
    assert response.status_code == 422


def test_duplicate_pending_conflict(client: TestClient, tenant: dict[str, object]) -> None:
    payload = {"email": "dup@example.com", "role": "member"}
    first = client.post(_invites_url(tenant["id"]), json=payload, headers=_auth_headers("owner"))
    second = client.post(_invites_url(tenant["id"]), json=payload, headers=_auth_headers("owner"))
    assert first.status_code == 201
    assert second.status_code == 409


def test_inviting_existing_member_email_conflicts(
    client: TestClient, tenant: dict[str, object]
) -> None:
    # admin üyesinin e-postası: "admin@example.com" (identity email_snapshot).
    response = client.post(
        _invites_url(tenant["id"]),
        json={"email": "admin@example.com", "role": "member"},
        headers=_auth_headers("owner"),
    )
    assert response.status_code == 409


def test_idempotency_key_replay_returns_duplicate_without_token(
    client: TestClient, tenant: dict[str, object]
) -> None:
    headers = _auth_headers("owner", **{"Idempotency-Key": "abc-123"})
    payload = {"email": "idem@example.com", "role": "member"}
    first = client.post(_invites_url(tenant["id"]), json=payload, headers=headers)
    second = client.post(_invites_url(tenant["id"]), json=payload, headers=headers)
    assert first.status_code == 201 and first.json()["token"]
    assert second.status_code == 201
    body = second.json()
    assert body["duplicate"] is True
    assert body["token"] is None and body["accept_url"] is None


# --- list --------------------------------------------------------------------


def test_list_returns_pending_without_token(client: TestClient, tenant: dict[str, object]) -> None:
    client.post(
        _invites_url(tenant["id"]),
        json={"email": "list1@example.com", "role": "member"},
        headers=_auth_headers("owner"),
    )
    response = client.get(_invites_url(tenant["id"]), headers=_auth_headers("admin"))
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["invited_email"] == "list1@example.com"
    assert "token" not in item
    assert "token_hash" not in item


def test_list_member_forbidden(client: TestClient, tenant: dict[str, object]) -> None:
    assert (
        client.get(_invites_url(tenant["id"]), headers=_auth_headers("member")).status_code == 403
    )


def test_list_non_member_not_found(client: TestClient, tenant: dict[str, object]) -> None:
    assert (
        client.get(_invites_url(tenant["id"]), headers=_auth_headers("stranger")).status_code == 404
    )


# --- revoke ------------------------------------------------------------------


def _create_invitation(client: TestClient, tenant_id: object, email: str = "r@example.com") -> str:
    response = client.post(
        _invites_url(tenant_id),
        json={"email": email, "role": "member"},
        headers=_auth_headers("owner"),
    )
    assert response.status_code == 201, response.text
    return response.json()["invitation_id"]


def test_owner_revokes_then_replay_idempotent(
    client: TestClient, tenant: dict[str, object]
) -> None:
    invitation_id = _create_invitation(client, tenant["id"])
    url = f"{_invites_url(tenant['id'])}/{invitation_id}/revoke"
    first = client.post(url, headers=_auth_headers("owner"))
    second = client.post(url, headers=_auth_headers("admin"))
    assert first.status_code == 200 and first.json()["status"] == "revoked"
    assert first.json()["duplicate"] is False
    assert second.status_code == 200 and second.json()["duplicate"] is True


def test_revoke_unknown_not_found(client: TestClient, tenant: dict[str, object]) -> None:
    url = f"{_invites_url(tenant['id'])}/{uuid4()}/revoke"
    assert client.post(url, headers=_auth_headers("owner")).status_code == 404


def test_revoke_member_forbidden(client: TestClient, tenant: dict[str, object]) -> None:
    invitation_id = _create_invitation(client, tenant["id"])
    url = f"{_invites_url(tenant['id'])}/{invitation_id}/revoke"
    assert client.post(url, headers=_auth_headers("member")).status_code == 403


def test_cross_tenant_revoke_is_not_found(
    client: TestClient, tenant: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    invitation_id = _create_invitation(client, tenant["id"], email="target@example.com")
    # Ayrı tenant B + owner_b; B'nin owner'ı A'nın davetini B path'inden revoke edemez.
    tenant_b, _ = create_tenant_with_owner(app_sessionmaker, owner_subject="owner_b")
    url = f"{_invites_url(tenant_b)}/{invitation_id}/revoke"
    assert client.post(url, headers=_auth_headers("owner_b")).status_code == 404
    # A'nın daveti hâlâ pending (B tarafından değiştirilmedi).
    rows = invitation_rows(app_sessionmaker, tenant["id"])  # type: ignore[arg-type]
    assert rows[0]["status"] == "pending"


def test_cross_tenant_list_isolation(
    client: TestClient, tenant: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    _create_invitation(client, tenant["id"], email="a-only@example.com")
    tenant_b, _ = create_tenant_with_owner(app_sessionmaker, owner_subject="owner_b")
    response = client.get(_invites_url(tenant_b), headers=_auth_headers("owner_b"))
    assert response.status_code == 200
    assert response.json()["items"] == []  # B, A'nın davetlerini GÖRMEZ


def test_rls_default_deny_without_tenant_context(
    client: TestClient, tenant: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    _create_invitation(client, tenant["id"], email="rls@example.com")
    # Tenant context YOKKEN app rolü hiçbir satır göremez (default deny).
    with app_sessionmaker() as s, s.begin():
        count = s.execute(text("SELECT count(*) FROM organization_invitations")).scalar_one()
    assert count == 0
