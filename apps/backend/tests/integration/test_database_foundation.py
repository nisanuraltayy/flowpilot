"""Database foundation + organization creation — GERÇEK PostgreSQL testleri.

RLS, atomiklik, rol güvenliği ve migration bu testlerde kanıtlanır. Docker/
Testcontainers gerektirir; atlanmaz.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

from flowpilot.modules.identity.domain.user import User
from flowpilot.modules.identity.infrastructure.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from flowpilot.modules.organization.application.commands import CreateOrganizationCommand
from flowpilot.modules.organization.application.handler import CreateOrganizationHandler
from flowpilot.modules.organization.domain.membership import Membership
from flowpilot.modules.organization.domain.organization import Organization
from flowpilot.modules.organization.domain.organization_name import OrganizationName
from flowpilot.modules.organization.infrastructure.persistence.unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from flowpilot.shared.clock import SystemClock
from flowpilot.shared.identifiers import MembershipId, TenantId, UserId
from flowpilot.shared.ids import UuidGenerator
from tests.integration._support import (
    ADMIN_PW,
    ADMIN_USER,
    DB_NAME,
    IMAGE,
    REPO_ROOT,
    load_provision_module,
)

pytestmark = pytest.mark.integration


class _SessionmakerUserDirectory:
    """Handler için UserDirectory — her sorguda kısa ömürlü app session açar."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def exists(self, user_id: UserId) -> bool:
        with self._session_factory() as session:
            return SqlAlchemyUserRepository(session).exists(user_id)


def _add_user(session_factory: sessionmaker[Session], user_id: UUID) -> None:
    with session_factory() as session:
        SqlAlchemyUserRepository(session).add(
            User(
                id=UserId(user_id),
                auth_provider=None,
                provider_subject=None,
                email_snapshot="actor@example.com",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()


def _handler(session_factory: sessionmaker[Session]) -> CreateOrganizationHandler:
    return CreateOrganizationHandler(
        unit_of_work=SqlAlchemyUnitOfWork(session_factory),
        user_directory=_SessionmakerUserDirectory(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def _visible_tenant_ids(session_factory: sessionmaker[Session], tenant_context: UUID) -> list[UUID]:
    with session_factory() as session:
        session.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"),
            {"v": str(tenant_context)},
        )
        return [row[0] for row in session.execute(text("SELECT id FROM organization_tenants"))]


# --------------------------------------------------------------------------- schema


def test_migration_created_expected_tables(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        tables = {
            row[0]
            for row in session.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }
    assert {
        "identity_users",
        "organization_tenants",
        "organization_memberships",
        "alembic_version",
    } <= tables


def test_app_role_is_not_privileged(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        row = session.execute(
            text(
                "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                "FROM pg_roles WHERE rolname = 'flowpilot_app'"
            )
        ).one()
    assert row == (False, False, False, False)


def test_rls_enabled_and_forced_on_tenant_tables(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    with app_sessionmaker() as session:
        for table in ("organization_tenants", "organization_memberships"):
            enabled, forced = session.execute(
                text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"),
                {"t": table},
            ).one()
            assert (enabled, forced) == (True, True), table


# --------------------------------------------------------------------------- use-case


def test_create_organization_persists_tenant_and_owner_membership(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    actor = uuid4()
    _add_user(app_sessionmaker, actor)

    result = _handler(app_sessionmaker).handle(CreateOrganizationCommand(actor, "Acme"))

    with app_sessionmaker() as session:
        session.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"),
            {"v": str(result.tenant_id)},
        )
        tenant = session.execute(
            text("SELECT name, status, created_by_user_id FROM organization_tenants WHERE id = :i"),
            {"i": result.tenant_id},
        ).one()
        assert tenant.name == "Acme"
        assert tenant.status == "active"
        assert tenant.created_by_user_id == actor

        memberships = session.execute(
            text(
                "SELECT id, role, status, user_id "
                "FROM organization_memberships WHERE tenant_id = :t"
            ),
            {"t": result.tenant_id},
        ).all()
    assert len(memberships) == 1
    assert memberships[0].id == result.owner_membership_id
    assert memberships[0].role == "owner"
    assert memberships[0].status == "active"
    assert memberships[0].user_id == actor


def test_missing_actor_is_rejected(app_sessionmaker: sessionmaker[Session]) -> None:
    from flowpilot.modules.organization.application.errors import ActorNotFoundError

    unknown_actor = uuid4()  # kullanıcı EKLENMEDİ
    with pytest.raises(ActorNotFoundError):
        _handler(app_sessionmaker).handle(CreateOrganizationCommand(unknown_actor, "Acme"))


def test_duplicate_membership_is_blocked_by_database(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    actor = uuid4()
    _add_user(app_sessionmaker, actor)
    result = _handler(app_sessionmaker).handle(CreateOrganizationCommand(actor, "Acme"))

    with (
        pytest.raises(IntegrityError),
        SqlAlchemyUnitOfWork(app_sessionmaker) as uow,
    ):
        uow.set_tenant_context(result.tenant_id)
        uow.organizations.add_membership(
            Membership.create_owner(
                id=MembershipId(uuid4()),
                tenant_id=TenantId(result.tenant_id),
                user_id=UserId(actor),
                created_at=datetime.now(UTC),
            )
        )
        uow.commit()


def test_rollback_leaves_no_partial_tenant(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    actor = uuid4()
    _add_user(app_sessionmaker, actor)
    ghost_tenant = uuid4()

    with (
        pytest.raises(RuntimeError),
        SqlAlchemyUnitOfWork(app_sessionmaker) as uow,
    ):
        uow.set_actor_context(actor)
        uow.organizations.add_tenant(
            Organization.create(
                id=TenantId(ghost_tenant),
                name=OrganizationName("Ghost"),
                created_by=UserId(actor),
                created_at=datetime.now(UTC),
            )
        )
        raise RuntimeError("commit oncesi simule edilen hata")

    assert _visible_tenant_ids(app_sessionmaker, ghost_tenant) == []


# --------------------------------------------------------------------------- RLS


def test_missing_tenant_context_returns_no_rows(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    actor = uuid4()
    _add_user(app_sessionmaker, actor)
    _handler(app_sessionmaker).handle(CreateOrganizationCommand(actor, "Acme"))

    with app_sessionmaker() as session:
        rows = session.execute(text("SELECT id FROM organization_tenants")).all()
    assert rows == []


def test_tenant_a_cannot_read_tenant_b(app_sessionmaker: sessionmaker[Session]) -> None:
    actor_a, actor_b = uuid4(), uuid4()
    _add_user(app_sessionmaker, actor_a)
    _add_user(app_sessionmaker, actor_b)
    result_a = _handler(app_sessionmaker).handle(CreateOrganizationCommand(actor_a, "A"))
    result_b = _handler(app_sessionmaker).handle(CreateOrganizationCommand(actor_b, "B"))

    visible = _visible_tenant_ids(app_sessionmaker, result_a.tenant_id)
    assert result_a.tenant_id in visible
    assert result_b.tenant_id not in visible

    # Tenant B ID'sini DOĞRUDAN kullanmak da erişim sağlamaz.
    with app_sessionmaker() as session:
        session.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"),
            {"v": str(result_a.tenant_id)},
        )
        direct = session.execute(
            text("SELECT id FROM organization_tenants WHERE id = :i"),
            {"i": result_b.tenant_id},
        ).all()
    assert direct == []


def test_correct_context_sees_own_tenant_and_membership(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    actor = uuid4()
    _add_user(app_sessionmaker, actor)
    result = _handler(app_sessionmaker).handle(CreateOrganizationCommand(actor, "Acme"))

    with app_sessionmaker() as session:
        session.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"),
            {"v": str(result.tenant_id)},
        )
        tenants = session.execute(text("SELECT id FROM organization_tenants")).all()
        memberships = session.execute(text("SELECT id FROM organization_memberships")).all()
    assert [r[0] for r in tenants] == [result.tenant_id]
    assert [r[0] for r in memberships] == [result.owner_membership_id]


def test_table_owner_does_not_bypass_forced_rls(
    app_sessionmaker: sessionmaker[Session],
    migrator_sessionmaker: sessionmaker[Session],
) -> None:
    # Veri app rolüyle oluşturulur.
    actor = uuid4()
    _add_user(app_sessionmaker, actor)
    _handler(app_sessionmaker).handle(CreateOrganizationCommand(actor, "Acme"))

    # Migrator tabloların SAHİBİDİR; FORCE RLS nedeniyle context'siz VERİ GÖREMEZ.
    with migrator_sessionmaker() as session:
        rows = session.execute(text("SELECT id FROM organization_tenants")).all()
    assert rows == []


# --------------------------------------------------------------------------- downgrade


def test_migration_downgrade_leaves_no_app_tables() -> None:
    # İzole, tek kullanımlık container — diğer testleri etkilemez.
    provision = load_provision_module()
    with PostgresContainer(
        IMAGE, username=ADMIN_USER, password=ADMIN_PW, dbname=DB_NAME, driver="psycopg"
    ) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        with psycopg.connect(
            host=host,
            port=int(port),
            dbname=DB_NAME,
            user=ADMIN_USER,
            password=ADMIN_PW,
            autocommit=True,
        ) as admin_conn:
            provision.provision_roles(
                admin_conn,
                database=DB_NAME,
                app_password="dg_app_pw",
                migrator_password="dg_migrator_pw",
            )
        migrator_url = (
            f"postgresql+psycopg://flowpilot_migrator:dg_migrator_pw@{host}:{port}/{DB_NAME}"
        )
        cfg = Config(str(Path(REPO_ROOT) / "apps" / "backend" / "alembic.ini"))
        cfg.set_main_option(
            "script_location", str(Path(REPO_ROOT) / "apps" / "backend" / "migrations")
        )
        cfg.set_main_option("sqlalchemy.url", migrator_url)

        command.upgrade(cfg, "head")
        engine = create_engine(migrator_url)
        try:
            with engine.connect() as conn:
                after_upgrade = {
                    row[0]
                    for row in conn.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                    )
                }
            assert {
                "identity_users",
                "organization_tenants",
                "organization_memberships",
            } <= after_upgrade

            command.downgrade(cfg, "base")
            with engine.connect() as conn:
                after_downgrade = {
                    row[0]
                    for row in conn.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                    )
                }
        finally:
            engine.dispose()

    assert "identity_users" not in after_downgrade
    assert "organization_tenants" not in after_downgrade
    assert "organization_memberships" not in after_downgrade
