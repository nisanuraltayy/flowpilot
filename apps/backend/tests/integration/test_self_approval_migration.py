"""0011 migration — blocked status/reason/index + downgrade + tek head.

Fresh 0001→0011 session fixture'ı tarafından uygulanır; bu testler 0011'in eklediği yapıyı
ve 0011→0010→head yolunu doğrular. 0001–0010 IMMUTABLE kalır.
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration._support import REPO_ROOT
from tests.integration.conftest import DatabaseHandle

TABLE = "workflow_runtime_tasks"
STATUS_CK = "ck_workflow_runtime_tasks_status_valid"
REASON_CK = "ck_workflow_runtime_tasks_blocked_reason_valid"


def _cfg(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "apps" / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "apps" / "backend" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_single_head_is_0011(database: DatabaseHandle) -> None:
    engine = create_engine(database.migrator_url)
    with engine.connect() as conn:
        heads = {r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version")).all()}
    engine.dispose()
    assert heads == {"0011"}, f"beklenen tek head 0011, bulunan: {heads}"


def test_status_check_accepts_blocked(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        definition = session.execute(
            text(
                f"SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = '{STATUS_CK}'"  # noqa: S608
            )
        ).scalar_one()
    for value in ("pending", "active", "blocked", "approved", "rejected", "cancelled"):
        assert value in definition, f"status CHECK '{value}' değerini kabul etmiyor"


def test_blocked_reason_check_and_columns(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        reason_def = session.execute(
            text(
                f"SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = '{REASON_CK}'"  # noqa: S608
            )
        ).scalar_one()
        cols = {
            r[0]: r[1]
            for r in session.execute(
                text(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name IN ('blocked_reason','blocked_at')"
                ),
                {"t": TABLE},
            ).all()
        }
    assert "self_approval_no_eligible_assignee" in reason_def
    # Additive → yeni kolonlar NULLABLE (eski satırlar korunur).
    assert cols == {"blocked_reason": "YES", "blocked_at": "YES"}


def test_tenant_status_index_present(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        indexes = {
            r[0]
            for r in session.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
            ).all()
        }
    assert "ix_workflow_runtime_tasks_tenant_status" in indexes


def test_no_delete_grant(app_sessionmaker: sessionmaker[Session]) -> None:
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


def test_downgrade_to_0010_removes_blocked_then_upgrade_head(database: DatabaseHandle) -> None:
    cfg = _cfg(database.migrator_url)
    try:
        command.downgrade(cfg, "0010")
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
            status_def = conn.execute(
                text(
                    f"SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = '{STATUS_CK}'"  # noqa: S608, E501
                )
            ).scalar_one()
        engine.dispose()
        assert "blocked_reason" not in cols and "blocked_at" not in cols
        assert "blocked" not in status_def  # 0010'da status CHECK 'blocked' içermez
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
    assert "blocked_reason" in cols and "blocked_at" in cols
