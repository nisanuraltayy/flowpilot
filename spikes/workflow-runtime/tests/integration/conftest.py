"""Spike integration altyapısı — GERÇEK PostgreSQL (Testcontainers).

- Local development veritabanına DOKUNMAZ; her run izole container.
- Docker yoksa Testcontainers HATA verir (sessizce atlanmaz) — bilinçli.
- Roller: spike_app + spike_worker (ikisi de NOSUPERUSER + NOBYPASSRLS).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

from spike_runtime.schema import (
    APP_ROLE,
    TENANT_TABLES,
    WORKER_ROLE,
    create_roles,
    create_schema,
)

IMAGE = "postgres:17.10-alpine"
ADMIN_USER = "spike_admin"
ADMIN_PW = "spike-admin-local-test-only"
APP_PW = "spike-app-local-test-only"
WORKER_PW = "spike-worker-local-test-only"
DB_NAME = "spike_runtime_db"

# Deterministik sabit test saati (tüm engine komutları clock-injected'tır).
T0 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)


@dataclass(frozen=True)
class SpikeDatabase:
    admin_url: str
    app_url: str
    worker_url: str


@pytest.fixture(scope="session")
def database() -> Iterator[SpikeDatabase]:
    with PostgresContainer(
        IMAGE, username=ADMIN_USER, password=ADMIN_PW, dbname=DB_NAME, driver="psycopg"
    ) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)

        def url(user: str, pw: str) -> str:
            return f"postgresql+psycopg://{user}:{pw}@{host}:{port}/{DB_NAME}"

        admin_engine = create_engine(url(ADMIN_USER, ADMIN_PW))
        with admin_engine.begin() as conn:
            create_roles(conn, app_password=APP_PW, worker_password=WORKER_PW)
            create_schema(conn)
        admin_engine.dispose()

        yield SpikeDatabase(
            admin_url=url(ADMIN_USER, ADMIN_PW),
            app_url=url(APP_ROLE, APP_PW),
            worker_url=url(WORKER_ROLE, WORKER_PW),
        )


@pytest.fixture(scope="session")
def admin_engine(database: SpikeDatabase) -> Iterator[Engine]:
    engine = create_engine(database.admin_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine(database: SpikeDatabase) -> Iterator[Engine]:
    engine = create_engine(database.app_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def worker_engine(database: SpikeDatabase) -> Iterator[Engine]:
    engine = create_engine(database.worker_url)
    yield engine
    engine.dispose()


@pytest.fixture
def app_sf(app_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=app_engine)


@pytest.fixture
def worker_sf(worker_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=worker_engine)


@pytest.fixture
def admin_sf(admin_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=admin_engine)


@pytest.fixture(autouse=True)
def _clean_tables(admin_engine: Engine) -> Iterator[None]:
    yield
    with admin_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TENANT_TABLES)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def tenant_a() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def tenant_b() -> uuid.UUID:
    return uuid.uuid4()
