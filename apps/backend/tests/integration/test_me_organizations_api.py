"""GET /v1/me/organizations — GERÇEK PostgreSQL + fake auth.

Actor-scoped RLS (migration 0006): kullanıcı YALNIZ kendi aktif üyeliklerini görür;
inactive üyelik ve başka kullanıcının üyeliği görünmez. Token/secret sızmaz.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.api.deps import get_auth_provider, get_session_factory
from flowpilot.api.main import create_app
from flowpilot.config.settings import Settings
from flowpilot.modules.identity.application.auth import AuthenticatedIdentity
from flowpilot.modules.identity.domain.auth_provider import AuthProvider
from tests.unit.fakes import FakeAuthProvider

pytestmark = pytest.mark.integration

TOKEN_A = "me-token-a"
TOKEN_B = "me-token-b"
TOKEN_EMPTY = "me-token-empty"


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
    fake_auth = FakeAuthProvider(
        {
            TOKEN_A: _identity("me-sub-a"),
            TOKEN_B: _identity("me-sub-b"),
            TOKEN_EMPTY: _identity("me-sub-empty"),
        }
    )
    app.dependency_overrides[get_auth_provider] = lambda: fake_auth
    app.dependency_overrides[get_session_factory] = lambda: app_sessionmaker
    with TestClient(app) as test_client:
        yield test_client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_org(client: TestClient, token: str, name: str) -> str:
    resp = client.post("/v1/organizations", json={"name": name}, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    return str(resp.json()["organization_id"])


def _user_id_of(app_sessionmaker: sessionmaker[Session], subject: str) -> UUID:
    with app_sessionmaker() as s:
        row = s.execute(
            text(
                "SELECT id FROM identity_users "
                "WHERE auth_provider = 'supabase' AND provider_subject = :sub"
            ),
            {"sub": subject},
        ).one()
    return UUID(str(row.id))


def _seed_suspended_membership(
    app_sessionmaker: sessionmaker[Session], user_id: UUID, org_name: str
) -> None:
    """Aynı kullanıcı için farklı bir tenant'ta SUSPENDED üyelik oluşturur."""
    tenant_id = uuid4()
    with app_sessionmaker() as s, s.begin():
        s.execute(text("SELECT set_config('app.current_actor_id', :a, true)"), {"a": str(user_id)})
        s.execute(
            text(
                "INSERT INTO organization_tenants (id, name, status, created_by_user_id, "
                "created_at) VALUES (:id, :name, 'active', :actor, now())"
            ),
            {"id": str(tenant_id), "name": org_name, "actor": str(user_id)},
        )
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        s.execute(
            text(
                "INSERT INTO organization_memberships (id, tenant_id, user_id, role, status, "
                "created_at, updated_at, version) "
                "VALUES (:id, :t, :u, 'member', 'suspended', now(), now(), 1)"
            ),
            {"id": str(uuid4()), "t": str(tenant_id), "u": str(user_id)},
        )


def test_zero_memberships_returns_empty_list(client: TestClient) -> None:
    resp = client.get("/v1/me/organizations", headers=_auth(TOKEN_EMPTY))
    # Kullanıcı henüz hiç org oluşturmadıysa internal user da yoktur; ensure_user
    # her istekte user'ı oluşturur → boş liste döner (org yok).
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"items": []}


def test_single_active_membership_returned(client: TestClient) -> None:
    org_id = _create_org(client, TOKEN_A, "Acme")
    resp = client.get("/v1/me/organizations", headers=_auth(TOKEN_A))
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["organization_id"] == org_id
    assert items[0]["name"] == "Acme"
    assert items[0]["membership_kind"] == "owner"
    assert items[0]["membership_status"] == "active"


def test_multiple_active_memberships_returned(client: TestClient) -> None:
    org1 = _create_org(client, TOKEN_A, "Org Bir")
    org2 = _create_org(client, TOKEN_A, "Org Iki")
    resp = client.get("/v1/me/organizations", headers=_auth(TOKEN_A))
    assert resp.status_code == 200, resp.text
    ids = {item["organization_id"] for item in resp.json()["items"]}
    assert ids == {org1, org2}


def test_inactive_membership_not_listed(
    client: TestClient, app_sessionmaker: sessionmaker[Session]
) -> None:
    active_org = _create_org(client, TOKEN_A, "Aktif Org")
    user_id = _user_id_of(app_sessionmaker, "me-sub-a")
    _seed_suspended_membership(app_sessionmaker, user_id, "Askıya Alınmış Org")

    resp = client.get("/v1/me/organizations", headers=_auth(TOKEN_A))
    items = resp.json()["items"]
    ids = {item["organization_id"] for item in items}
    assert ids == {active_org}
    assert all(item["membership_status"] == "active" for item in items)


def test_other_users_memberships_not_visible(client: TestClient) -> None:
    _create_org(client, TOKEN_A, "A Org")
    b_org = _create_org(client, TOKEN_B, "B Org")

    a_items = client.get("/v1/me/organizations", headers=_auth(TOKEN_A)).json()["items"]
    a_ids = {item["organization_id"] for item in a_items}
    assert b_org not in a_ids
    assert all(item["name"] != "B Org" for item in a_items)


def test_missing_token_returns_401(client: TestClient) -> None:
    assert client.get("/v1/me/organizations").status_code == 401
