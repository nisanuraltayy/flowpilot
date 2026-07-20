"""Integration test altyapısı — GERÇEK PostgreSQL (Testcontainers).

- FlowPilot local development verisine DOKUNMAZ: her run izole bir container'da
  çalışır.
- Rolleri `scripts/provision_local_database.py` içindeki `provision_roles` ile
  oluşturur (kod tekrarı yok).
- Alembic migration'ı `flowpilot_migrator` rolüyle uygular.
- Testlere `flowpilot_app` (BYPASSRLS'siz) rolüyle bağlı bir sessionmaker verir.
- Docker yoksa Testcontainers HATA verir (sessizce atlanmaz) — bu bilinçlidir.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

from tests.integration._support import (
    ADMIN_PW,
    ADMIN_USER,
    APP_PW,
    DB_NAME,
    IMAGE,
    MIGRATOR_PW,
    REPO_ROOT,
    load_provision_module,
)


@dataclass(frozen=True)
class DatabaseHandle:
    app_url: str
    migrator_url: str


@pytest.fixture(scope="session")
def database() -> Iterator[DatabaseHandle]:
    provision = load_provision_module()
    with PostgresContainer(
        IMAGE,
        username=ADMIN_USER,
        password=ADMIN_PW,
        dbname=DB_NAME,
        driver="psycopg",
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
                app_password=APP_PW,
                migrator_password=MIGRATOR_PW,
            )

        migrator_url = (
            f"postgresql+psycopg://flowpilot_migrator:{MIGRATOR_PW}@{host}:{port}/{DB_NAME}"
        )
        app_url = f"postgresql+psycopg://flowpilot_app:{APP_PW}@{host}:{port}/{DB_NAME}"

        cfg = Config(str(REPO_ROOT / "apps" / "backend" / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "apps" / "backend" / "migrations"))
        cfg.set_main_option("sqlalchemy.url", migrator_url)
        command.upgrade(cfg, "head")

        yield DatabaseHandle(app_url=app_url, migrator_url=migrator_url)


@pytest.fixture
def app_sessionmaker(database: DatabaseHandle) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(database.app_url)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


@pytest.fixture
def migrator_sessionmaker(database: DatabaseHandle) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(database.migrator_url)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


@pytest.fixture
def runtime_service(app_sessionmaker: sessionmaker[Session]) -> object:
    """WorkflowRuntimeService, gerçek flowpilot_app (NOBYPASSRLS) sessionmaker'ı ile."""
    from tests.integration.workflow_support import build_service

    return build_service(app_sessionmaker)


@pytest.fixture
def tenant_a() -> UUID:
    return uuid4()


@pytest.fixture
def tenant_b() -> UUID:
    return uuid4()


_TRUNCATE_TABLES = (
    "audit_entries",
    "approval_decisions",
    "approval_role_assignments",
    "purchase_request_requests",
    "workflow_runtime_inbox",
    "workflow_runtime_timers",
    "workflow_runtime_events",
    "workflow_runtime_outbox",
    "workflow_runtime_tasks",
    "workflow_runtime_instances",
    "workflow_runtime_definition_versions",
    "workflow_runtime_definitions",
    "organization_invitations",
    "organization_memberships",
    "organization_tenants",
    "identity_users",
)


@pytest.fixture(autouse=True)
def _clean_tables(database: DatabaseHandle) -> Iterator[None]:
    """Her testten sonra app tablolarını temizler (migrator owner TRUNCATE eder)."""
    yield
    engine = create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {', '.join(_TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
    finally:
        engine.dispose()
