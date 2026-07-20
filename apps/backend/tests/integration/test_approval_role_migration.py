"""0010 migration — approval_role_assignments version/index/grant + backfill + downgrade.

Fresh 0001→0010 session fixture'ı tarafından uygulanır; bu testler 0010'un eklediği yapıyı,
backfill'i ve 0010→0009→head yolunu doğrular. 0001–0009 IMMUTABLE kalır.
"""

from __future__ import annotations

from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration._support import REPO_ROOT
from tests.integration.conftest import DatabaseHandle

TABLE = "approval_role_assignments"


def _alembic_config(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "apps" / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "apps" / "backend" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_single_head_is_0010(database: DatabaseHandle) -> None:
    engine = create_engine(database.migrator_url)
    with engine.connect() as conn:
        heads = {r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version")).all()}
    engine.dispose()
    assert heads == {"0010"}, f"beklenen tek head 0010, bulunan: {heads}"


def test_version_column_not_null(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        cols = {
            r[0]: (r[1], r[2])
            for r in session.execute(
                text(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns WHERE table_name = :t"
                ),
                {"t": TABLE},
            ).all()
        }
    assert "version" in cols and cols["version"][0] == "integer" and cols["version"][1] == "NO"
    assert "updated_at" in cols and cols["updated_at"][1] == "NO"


def test_rls_enabled_and_forced(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        row = session.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = :t AND relkind = 'r'"
            ),
            {"t": TABLE},
        ).one()
    assert row[0] is True and row[1] is True


def test_grants_no_delete_but_update(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        privileges = {
            r[0]
            for r in session.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_name = :t AND grantee = 'flowpilot_app'"
                ),
                {"t": TABLE},
            ).all()
        }
    assert {"SELECT", "INSERT", "UPDATE"} <= privileges
    assert "DELETE" not in privileges


def test_indexes_and_partial_unique_present(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        indexes = {
            r[0]
            for r in session.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
            ).all()
        }
    assert "ix_approval_role_assignments_tenant_role_status" in indexes
    assert "ix_approval_role_assignments_tenant_user_status" in indexes
    # Partial unique (tek aktif assignee) KORUNUR.
    assert "uq_approval_role_assignments_active" in indexes


def test_backfill_sets_version_one(database: DatabaseHandle) -> None:
    """0009 şemasında (version YOK) satır ekle → 0010'a yükselt → version=1."""
    cfg = _alembic_config(database.migrator_url)
    tenant_id = uuid4()
    actor_id = uuid4()
    assignment_id = uuid4()
    try:
        command.downgrade(cfg, "0009")
        engine = create_engine(database.migrator_url)
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.current_actor_id', :a, true)"), {"a": str(actor_id)}
            )
            conn.execute(
                text(
                    "INSERT INTO organization_tenants (id, name, status, created_by_user_id, "
                    "created_at) VALUES (:id, 'Backfill', 'active', :actor, now())"
                ),
                {"id": str(tenant_id), "actor": str(actor_id)},
            )
            conn.execute(
                text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
            conn.execute(
                text(
                    "INSERT INTO approval_role_assignments "
                    "(id, tenant_id, role_key, assigned_user_id, status, created_at, updated_at) "
                    "VALUES (:id, :t, 'finance', :u, 'active', now(), now())"
                ),
                {"id": str(assignment_id), "t": str(tenant_id), "u": str(actor_id)},
            )
        engine.dispose()
    finally:
        command.upgrade(cfg, "head")

    engine = create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY"))
        version = conn.execute(
            text(f"SELECT version FROM {TABLE} WHERE id = :i"),  # noqa: S608 — TABLE sabit
            {"i": str(assignment_id)},
        ).scalar_one()
        conn.execute(text(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY"))
    engine.dispose()
    assert version == 1, "version 1'e backfill edilmedi"


def test_downgrade_to_0009_removes_version_then_upgrade_head(database: DatabaseHandle) -> None:
    cfg = _alembic_config(database.migrator_url)
    try:
        command.downgrade(cfg, "0009")
        engine = create_engine(database.migrator_url)
        with engine.connect() as conn:
            cols = {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
                    ),
                    {"t": TABLE},
                ).all()
            }
            indexes = {
                r[0]
                for r in conn.execute(
                    text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
                ).all()
            }
        engine.dispose()
        assert "version" not in cols
        assert "ix_approval_role_assignments_tenant_role_status" not in indexes
        # Partial unique 0005'ten gelir; downgrade 0010 onu KORUR.
        assert "uq_approval_role_assignments_active" in indexes
    finally:
        command.upgrade(cfg, "head")
    engine = create_engine(database.migrator_url)
    with engine.connect() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                {"t": TABLE},
            ).all()
        }
    engine.dispose()
    assert "version" in cols
