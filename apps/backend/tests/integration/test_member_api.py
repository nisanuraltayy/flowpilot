"""Üye yönetimi API — GERÇEK PostgreSQL (Testcontainers) + fake auth.

GET listeleme + PATCH güncelleme; authorization, invariant ve güvenlik uçtan uca.
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
    "admin2": "tok-admin2",
    "member": "tok-member",
    "member2": "tok-member2",
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
    admin2_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="admin2", role="admin")
    member_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="member", role="member")
    member2_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="member2", role="member")
    return {
        "id": tenant_id,
        "owner": owner_id,
        "admin": admin_id,
        "admin2": admin2_id,
        "member": member_id,
        "member2": member2_id,
    }


def _members_url(tenant_id: object) -> str:
    return f"/v1/organizations/{tenant_id}/members"


# =============================== GET ========================================


def test_owner_lists_members_no_sensitive_fields(
    client: TestClient, org: dict[str, object]
) -> None:
    resp = client.get(_members_url(org["id"]), headers=_bearer("owner"))
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 5  # owner + admin + admin2 + member + member2
    for item in items:
        assert set(item) == {
            "membership_id",
            "user_id",
            "email",
            "role",
            "status",
            "version",
            "created_at",
            "updated_at",
        }
        assert "provider_subject" not in item and "auth_provider" not in item
    assert "supabase" not in resp.text


def test_admin_lists_members(client: TestClient, org: dict[str, object]) -> None:
    assert client.get(_members_url(org["id"]), headers=_bearer("admin")).status_code == 200


def test_member_list_forbidden(client: TestClient, org: dict[str, object]) -> None:
    assert client.get(_members_url(org["id"]), headers=_bearer("member")).status_code == 403


def test_stranger_list_not_found(client: TestClient, org: dict[str, object]) -> None:
    assert client.get(_members_url(org["id"]), headers=_bearer("stranger")).status_code == 404


def test_list_requires_auth(client: TestClient, org: dict[str, object]) -> None:
    assert client.get(_members_url(org["id"])).status_code == 401


def test_list_pagination_limit(client: TestClient, org: dict[str, object]) -> None:
    resp = client.get(f"{_members_url(org['id'])}?limit=2", headers=_bearer("owner"))
    assert resp.status_code == 200 and len(resp.json()["items"]) == 2


def test_list_cross_tenant_isolation(
    client: TestClient, org: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    tenant_b, _ = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-b")
    # owner (tenant A) is not a member of B → 404, and cannot see B's members.
    assert client.get(_members_url(tenant_b), headers=_bearer("owner")).status_code == 404


# =============================== PATCH ======================================


def _patch(client: TestClient, tenant: object, user: object, who: str, **body: object) -> object:
    return client.patch(f"{_members_url(tenant)}/{user}", json=body, headers=_bearer(who))


def test_owner_promotes_member_to_admin(client: TestClient, org: dict[str, object]) -> None:
    resp = _patch(client, org["id"], org["member"], "owner", role="admin", expected_version=1)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "admin" and body["version"] == 2 and body["duplicate"] is False


def test_admin_promotes_member_to_admin(client: TestClient, org: dict[str, object]) -> None:
    resp = _patch(client, org["id"], org["member"], "admin", role="admin", expected_version=1)
    assert resp.status_code == 200 and resp.json()["role"] == "admin"


def test_admin_cannot_touch_admin_target(client: TestClient, org: dict[str, object]) -> None:
    # admin actor, BAŞKA bir admin'i (admin2) hedefler → 403 (admin yalnız member yönetir).
    resp = _patch(client, org["id"], org["admin2"], "admin", status="suspended", expected_version=1)
    assert resp.status_code == 403


def test_admin_cannot_grant_owner(client: TestClient, org: dict[str, object]) -> None:
    resp = _patch(client, org["id"], org["member"], "admin", role="owner", expected_version=1)
    assert resp.status_code == 403


def test_member_actor_forbidden(client: TestClient, org: dict[str, object]) -> None:
    resp = _patch(client, org["id"], org["member2"], "member", role="admin", expected_version=1)
    assert resp.status_code == 403


def test_stranger_not_found(client: TestClient, org: dict[str, object]) -> None:
    resp = _patch(client, org["id"], org["member"], "stranger", role="admin", expected_version=1)
    assert resp.status_code == 404


def test_patch_requires_auth(client: TestClient, org: dict[str, object]) -> None:
    resp = client.patch(
        f"{_members_url(org['id'])}/{org['member']}", json={"role": "admin", "expected_version": 1}
    )
    assert resp.status_code == 401


def test_self_mutation_conflict(client: TestClient, org: dict[str, object]) -> None:
    resp = _patch(client, org["id"], org["owner"], "owner", role="admin", expected_version=1)
    assert resp.status_code == 409


def test_target_not_found(client: TestClient, org: dict[str, object]) -> None:
    resp = _patch(client, org["id"], uuid4(), "owner", role="admin", expected_version=1)
    assert resp.status_code == 404


def test_stale_version_conflict(client: TestClient, org: dict[str, object]) -> None:
    resp = _patch(client, org["id"], org["member"], "owner", role="admin", expected_version=99)
    assert resp.status_code == 409


def test_suspend_then_removed_terminal(client: TestClient, org: dict[str, object]) -> None:
    s = _patch(client, org["id"], org["member"], "owner", status="suspended", expected_version=1)
    assert s.status_code == 200 and s.json()["status"] == "suspended"
    r = _patch(client, org["id"], org["member"], "owner", status="removed", expected_version=2)
    assert r.status_code == 200 and r.json()["status"] == "removed"
    # removed terminal: rol değişimi → 409.
    conflict = _patch(client, org["id"], org["member"], "owner", role="admin", expected_version=3)
    assert conflict.status_code == 409


def test_noop_returns_duplicate(client: TestClient, org: dict[str, object]) -> None:
    # member zaten active → status=active no-op → duplicate=true, version değişmez.
    resp = _patch(client, org["id"], org["member"], "owner", status="active", expected_version=1)
    assert resp.status_code == 200
    assert resp.json()["duplicate"] is True and resp.json()["version"] == 1


def test_invalid_status_422(client: TestClient, org: dict[str, object]) -> None:
    resp = _patch(client, org["id"], org["member"], "owner", status="banished", expected_version=1)
    assert resp.status_code == 422


def test_missing_role_and_status_422(client: TestClient, org: dict[str, object]) -> None:
    resp = _patch(client, org["id"], org["member"], "owner", expected_version=1)
    assert resp.status_code == 422


def test_cross_tenant_update_not_found(
    client: TestClient, org: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    tenant_b, _ = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-b")
    # owner (A) B'nin bir üyesini güncelleyemez; B'de üye değil → 404.
    resp = _patch(client, tenant_b, org["member"], "owner", role="admin", expected_version=1)
    assert resp.status_code == 404


def test_suspend_with_approval_responsibility_conflict(
    client: TestClient, org: dict[str, object], app_sessionmaker: sessionmaker[Session]
) -> None:
    from sqlalchemy import text

    # member'a aktif bir approval_role_assignment ata → suspend/remove 409.
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(org["id"])}
        )
        s.execute(
            text(
                "INSERT INTO approval_role_assignments "
                "(id, tenant_id, role_key, assigned_user_id, status, created_at, updated_at) "
                "VALUES (:id, :t, 'finance', :u, 'active', now(), now())"
            ),
            {"id": str(uuid4()), "t": str(org["id"]), "u": str(org["member"])},
        )
    resp = _patch(client, org["id"], org["member"], "owner", status="suspended", expected_version=1)
    assert resp.status_code == 409
