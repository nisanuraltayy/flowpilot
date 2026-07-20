"""Approval rol atama API — GERÇEK PostgreSQL (Testcontainers) + fake auth.

GET listeleme + PUT atama; authorization, invariant ve güvenlik uçtan uca.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.api.deps import get_auth_provider, get_session_factory
from flowpilot.api.main import create_app
from flowpilot.config.settings import Settings
from tests.integration.invitation_support import add_member, create_tenant_with_owner, identity_for
from tests.unit.fakes import FakeAuthProvider

pytestmark = pytest.mark.integration

TOKENS = {
    "owner": "tok-owner",
    "admin": "tok-admin",
    "member": "tok-member",
    "target": "tok-target",
    "target2": "tok-target2",
    "suspended": "tok-suspended",
    "stranger": "tok-stranger",
}


def _bearer(who: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[who]}"}


@pytest.fixture
def client(app_sessionmaker: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(settings=Settings(_env_file=None, app_environment="test"))
    fake_auth = FakeAuthProvider({token: identity_for(name) for name, token in TOKENS.items()})
    app.dependency_overrides[get_auth_provider] = lambda: fake_auth
    app.dependency_overrides[get_session_factory] = lambda: app_sessionmaker
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def org(app_sessionmaker: sessionmaker[Session]) -> dict[str, object]:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    admin_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="admin", role="admin")
    member_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="member", role="member")
    target_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="target", role="member")
    target2_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="target2", role="admin")
    suspended_id = add_member(
        app_sessionmaker,
        tenant_id=tenant_id,
        subject="suspended",
        role="member",
        status="suspended",
    )
    return {
        "id": tenant_id,
        "owner": owner_id,
        "admin": admin_id,
        "member": member_id,
        "target": target_id,
        "target2": target2_id,
        "suspended": suspended_id,
    }


def _roles_url(tenant_id: object) -> str:
    return f"/v1/organizations/{tenant_id}/approval-roles"


def _put(client: TestClient, tenant: object, role: str, who: str, **body: object) -> object:
    return client.put(f"{_roles_url(tenant)}/{role}", json=body, headers=_bearer(who))


# =============================== PUT (assign) ==============================


def test_owner_assigns_finance_creates_v1(client: TestClient, org: dict[str, object]) -> None:
    resp = _put(client, org["id"], "finance", "owner", user_id=str(org["target"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role_key"] == "finance"
    assert body["assigned_user_id"] == str(org["target"])
    assert body["assigned_user_email"] == "target@example.com"
    assert body["version"] == 1 and body["duplicate"] is False


def test_admin_assigns_team_manager(client: TestClient, org: dict[str, object]) -> None:
    resp = _put(client, org["id"], "team_manager", "admin", user_id=str(org["target"]))
    assert resp.status_code == 200 and resp.json()["assigned_user_id"] == str(org["target"])


def test_member_actor_forbidden(client: TestClient, org: dict[str, object]) -> None:
    resp = _put(client, org["id"], "finance", "member", user_id=str(org["target"]))
    assert resp.status_code == 403


def test_stranger_not_found(client: TestClient, org: dict[str, object]) -> None:
    resp = _put(client, org["id"], "finance", "stranger", user_id=str(org["target"]))
    assert resp.status_code == 404


def test_put_requires_auth(client: TestClient, org: dict[str, object]) -> None:
    resp = client.put(f"{_roles_url(org['id'])}/finance", json={"user_id": str(org["target"])})
    assert resp.status_code == 401


def test_invalid_role_key_422(client: TestClient, org: dict[str, object]) -> None:
    resp = _put(client, org["id"], "ceo", "owner", user_id=str(org["target"]))
    assert resp.status_code == 422


def test_target_not_member_404(client: TestClient, org: dict[str, object]) -> None:
    resp = _put(client, org["id"], "finance", "owner", user_id=str(uuid4()))
    assert resp.status_code == 404


def test_target_suspended_409(client: TestClient, org: dict[str, object]) -> None:
    resp = _put(client, org["id"], "finance", "owner", user_id=str(org["suspended"]))
    assert resp.status_code == 409


def test_noop_returns_duplicate(client: TestClient, org: dict[str, object]) -> None:
    first = _put(client, org["id"], "finance", "owner", user_id=str(org["target"]))
    assert first.status_code == 200 and first.json()["version"] == 1
    again = _put(
        client, org["id"], "finance", "owner", user_id=str(org["target"]), expected_version=1
    )
    assert again.status_code == 200
    assert again.json()["duplicate"] is True and again.json()["version"] == 1


def test_reassign_bumps_version(client: TestClient, org: dict[str, object]) -> None:
    _put(client, org["id"], "finance", "owner", user_id=str(org["target"]))
    resp = _put(
        client, org["id"], "finance", "owner", user_id=str(org["target2"]), expected_version=1
    )
    assert resp.status_code == 200
    assert resp.json()["assigned_user_id"] == str(org["target2"]) and resp.json()["version"] == 2


def test_stale_version_409(client: TestClient, org: dict[str, object]) -> None:
    _put(client, org["id"], "finance", "owner", user_id=str(org["target"]))
    resp = _put(
        client, org["id"], "finance", "owner", user_id=str(org["target2"]), expected_version=99
    )
    assert resp.status_code == 409


def test_expected_version_required_when_active_exists_422(
    client: TestClient, org: dict[str, object]
) -> None:
    _put(client, org["id"], "finance", "owner", user_id=str(org["target"]))
    # aktif atama var, expected_version yok → 422.
    resp = _put(client, org["id"], "finance", "owner", user_id=str(org["target2"]))
    assert resp.status_code == 422


def test_cross_tenant_assign_not_found(
    client: TestClient, org: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    tenant_b, _ = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-b")
    resp = _put(client, tenant_b, "finance", "owner", user_id=str(org["target"]))
    assert resp.status_code == 404  # owner A, B'de üye değil


# =============================== GET (list) ================================


def test_owner_lists_assignments_no_sensitive_fields(
    client: TestClient, org: dict[str, object]
) -> None:
    _put(client, org["id"], "finance", "owner", user_id=str(org["target"]))
    resp = client.get(_roles_url(org["id"]), headers=_bearer("owner"))
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    finance = next(i for i in items if i["role_key"] == "finance")
    assert finance["assigned_user_id"] == str(org["target"])
    assert finance["assigned_user_email"] == "target@example.com"
    for item in items:
        assert set(item) == {
            "assignment_id",
            "role_key",
            "assigned_user_id",
            "assigned_user_email",
            "status",
            "version",
            "created_at",
            "updated_at",
        }
    assert "provider_subject" not in resp.text and "supabase" not in resp.text


def test_admin_lists(client: TestClient, org: dict[str, object]) -> None:
    assert client.get(_roles_url(org["id"]), headers=_bearer("admin")).status_code == 200


def test_member_list_forbidden(client: TestClient, org: dict[str, object]) -> None:
    assert client.get(_roles_url(org["id"]), headers=_bearer("member")).status_code == 403


def test_stranger_list_not_found(client: TestClient, org: dict[str, object]) -> None:
    assert client.get(_roles_url(org["id"]), headers=_bearer("stranger")).status_code == 404


def test_list_requires_auth(client: TestClient, org: dict[str, object]) -> None:
    assert client.get(_roles_url(org["id"])).status_code == 401


def test_list_deterministic_role_order(client: TestClient, org: dict[str, object]) -> None:
    _put(client, org["id"], "general_manager", "owner", user_id=str(org["target"]))
    _put(client, org["id"], "team_manager", "owner", user_id=str(org["target"]))
    _put(client, org["id"], "finance", "owner", user_id=str(org["target"]))
    resp = client.get(_roles_url(org["id"]), headers=_bearer("owner"))
    order = [i["role_key"] for i in resp.json()["items"]]
    assert order == ["team_manager", "finance", "general_manager"]
