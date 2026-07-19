"""0003 migration — tablo/index/constraint, rol güvenliği, RLS, downgrade/upgrade.

`database` fixture'ı Testcontainers'ta 0001→0002→0003'ü head'e kadar uygular;
bu testler sonucu doğrular. Docker yoksa fixture HATA verir (sessizce atlanmaz).
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration._support import REPO_ROOT
from tests.integration.conftest import DatabaseHandle

RUNTIME_TABLES = (
    "workflow_runtime_definitions",
    "workflow_runtime_definition_versions",
    "workflow_runtime_instances",
    "workflow_runtime_tasks",
    "workflow_runtime_events",
    "workflow_runtime_outbox",
    "workflow_runtime_inbox",
    "workflow_runtime_timers",
)


def test_all_runtime_tables_exist(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        rows = session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE 'workflow_runtime_%'"
            )
        ).all()
    present = {r[0] for r in rows}
    assert set(RUNTIME_TABLES) <= present


def test_rls_enabled_and_forced_on_all_runtime_tables(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    with app_sessionmaker() as session:
        rows = session.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname LIKE 'workflow_runtime_%' AND relkind = 'r'"
            )
        ).all()
    by_name = {r[0]: (r[1], r[2]) for r in rows}
    for table in RUNTIME_TABLES:
        enabled, forced = by_name[table]
        assert enabled is True, f"{table}: RLS ENABLE yok"
        assert forced is True, f"{table}: RLS FORCE yok"


def test_app_role_has_no_bypassrls_or_superuser(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        row = session.execute(
            text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = 'flowpilot_app'")
        ).one()
    assert row[0] is False, "flowpilot_app BYPASSRLS taşıyamaz"
    assert row[1] is False, "flowpilot_app superuser olamaz"


def test_key_indexes_and_constraints_present(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        indexes = {
            r[0]
            for r in session.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename LIKE 'workflow_runtime_%'")
            ).all()
        }
    assert "ix_workflow_runtime_outbox_status" in indexes
    assert "ix_workflow_runtime_timers_due" in indexes
    assert "ix_workflow_runtime_instances_tenant_status" in indexes
    # Duplicate task koruması (unique) + outbox event_id unique.
    assert "uq_workflow_runtime_tasks_instance_id" in indexes
    assert "uq_workflow_runtime_outbox_event_id" in indexes


def test_downgrade_then_upgrade_is_safe(database: DatabaseHandle) -> None:
    """0003 → 0002 → 0003: geçici DB'de güvenli (idempotent şema)."""
    cfg = Config(str(REPO_ROOT / "apps" / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "apps" / "backend" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database.migrator_url)
    try:
        command.downgrade(cfg, "0002")
        from sqlalchemy import create_engine

        engine = create_engine(database.migrator_url)
        with engine.connect() as conn:
            remaining = conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name LIKE 'workflow_runtime_%'"
                )
            ).scalar_one()
        engine.dispose()
        assert remaining == 0, "downgrade runtime tablolarını bırakmamalı"
    finally:
        command.upgrade(cfg, "head")  # sonraki testler için head'e geri al
