"""Auth + organization API — GERÇEK PostgreSQL (Testcontainers) testleri.

Fake auth provider + gerçek repository/UoW/DB: HTTP akışı uçtan uca doğrulanır.
Gerçek Supabase ağına ÇAĞRI YAPILMAZ.
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
from flowpilot.modules.identity.application.ensure_user import EnsureAuthenticatedUserHandler
from flowpilot.modules.identity.domain.auth_provider import AuthProvider
from flowpilot.modules.identity.infrastructure.persistence.unit_of_work import (
    SqlAlchemyIdentityUnitOfWork,
)
from flowpilot.shared.clock import SystemClock
from flowpilot.shared.ids import UuidGenerator
from tests.unit.fakes import FakeAuthProvider

pytestmark = pytest.mark.integration

TOKEN_A = "integration-token-a"
TOKEN_B = "integration-token-b"


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
        {TOKEN_A: _identity("supabase-sub-a"), TOKEN_B: _identity("supabase-sub-b")}
    )
    app.dependency_overrides[get_auth_provider] = lambda: fake_auth
    app.dependency_overrides[get_session_factory] = lambda: app_sessionmaker
    with TestClient(app) as test_client:
        yield test_client


def _tenant_row(session_factory: sessionmaker[Session], tenant_id: str) -> tuple[str, str] | None:
    with session_factory() as session:
        session.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"), {"v": tenant_id}
        )
        row = session.execute(
            text("SELECT name, status FROM organization_tenants WHERE id = :i"),
            {"i": tenant_id},
        ).first()
        return (row.name, row.status) if row else None


def test_http_flow_creates_organization_and_owner_membership(
    client: TestClient, app_sessionmaker: sessionmaker[Session]
) -> None:
    response = client.post(
        "/v1/organizations",
        json={"name": "  Acme Teknoloji  "},
        headers={"Authorization": f"Bearer {TOKEN_A}"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"organization_id", "owner_membership_id", "name"}
    assert body["name"] == "Acme Teknoloji"  # normalize edilmis ad

    # Tenant gercekten olustu (RLS context ile okunur).
    assert _tenant_row(app_sessionmaker, body["organization_id"]) == (
        "Acme Teknoloji",
        "active",
    )

    # Owner membership ACTIVE ve dogru kullaniciya bagli.
    with app_sessionmaker() as session:
        session.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"),
            {"v": body["organization_id"]},
        )
        membership = session.execute(
            text(
                "SELECT id, role, status, user_id FROM organization_memberships "
                "WHERE tenant_id = :t"
            ),
            {"t": body["organization_id"]},
        ).one()
        assert str(membership.id) == body["owner_membership_id"]
        assert membership.role == "owner"
        assert membership.status == "active"

        # Internal user, provider subject'e esleniyor.
        user = session.execute(
            text(
                "SELECT id FROM identity_users "
                "WHERE auth_provider = 'supabase' AND provider_subject = 'supabase-sub-a'"
            )
        ).one()
        assert user.id == membership.user_id


def test_same_user_can_create_multiple_organizations(
    client: TestClient, app_sessionmaker: sessionmaker[Session]
) -> None:
    first = client.post(
        "/v1/organizations",
        json={"name": "Org Bir"},
        headers={"Authorization": f"Bearer {TOKEN_A}"},
    )
    second = client.post(
        "/v1/organizations",
        json={"name": "Org Iki"},
        headers={"Authorization": f"Bearer {TOKEN_A}"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["organization_id"] != second.json()["organization_id"]

    # Ayni subject icin TEK internal user olustu (idempotent sync).
    with app_sessionmaker() as session:
        count = session.execute(
            text(
                "SELECT count(*) FROM identity_users "
                "WHERE auth_provider = 'supabase' AND provider_subject = 'supabase-sub-a'"
            )
        ).scalar_one()
    assert count == 1


def test_missing_token_gets_401_and_no_rows_written(
    client: TestClient, app_sessionmaker: sessionmaker[Session]
) -> None:
    response = client.post("/v1/organizations", json={"name": "Hacker Org"})

    assert response.status_code == 401
    with app_sessionmaker() as session:
        users = session.execute(text("SELECT count(*) FROM identity_users")).scalar_one()
    assert users == 0  # auth basarisizken DB'ye HICBIR sey yazilmadi


def test_invalid_name_via_http_returns_422_and_no_partial_rows(
    client: TestClient, app_sessionmaker: sessionmaker[Session]
) -> None:
    response = client.post(
        "/v1/organizations",
        json={"name": "   "},
        headers={"Authorization": f"Bearer {TOKEN_A}"},
    )

    assert response.status_code == 422
    with app_sessionmaker() as session:
        session.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"), {"v": str(uuid4())}
        )
        tenants = session.execute(text("SELECT count(*) FROM organization_tenants")).scalar_one()
    assert tenants == 0


def test_provider_subject_unique_constraint_holds(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    from flowpilot.modules.identity.application.errors import DuplicateProviderIdentityError
    from flowpilot.modules.identity.domain.user import User
    from flowpilot.modules.identity.infrastructure.persistence.user_repository import (
        SqlAlchemyUserRepository,
    )
    from flowpilot.shared.identifiers import UserId

    def _user() -> User:
        return User(
            id=UserId(uuid4()),
            auth_provider=AuthProvider.SUPABASE,
            provider_subject="dup-subject",
            email_snapshot=None,
            created_at=datetime.now(UTC),
        )

    with app_sessionmaker() as session:
        SqlAlchemyUserRepository(session).add(_user())
        session.commit()

    with app_sessionmaker() as session, pytest.raises(DuplicateProviderIdentityError):
        SqlAlchemyUserRepository(session).add(_user())


def test_ensure_user_is_idempotent_against_real_db(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    handler = EnsureAuthenticatedUserHandler(
        unit_of_work_factory=lambda: SqlAlchemyIdentityUnitOfWork(app_sessionmaker),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )

    first = handler.handle(_identity("idempotent-sub"))
    second = handler.handle(_identity("idempotent-sub"))
    third = handler.handle(  # e-posta degisse bile ayni user
        AuthenticatedIdentity(
            provider=AuthProvider.SUPABASE,
            provider_subject="idempotent-sub",
            email="changed@example.com",
            token_expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )

    assert isinstance(first, UUID)
    assert first == second == third


def test_api_connection_role_is_not_bypassrls(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    with app_sessionmaker() as session:
        row = session.execute(
            text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user")
        ).one()
    assert row == (False, False)
