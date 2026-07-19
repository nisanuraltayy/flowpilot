"""0004 migration — tablo/constraint/index/RLS, rol güvenliği, downgrade/upgrade."""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration._support import REPO_ROOT
from tests.integration.conftest import DatabaseHandle

TABLE = "purchase_request_requests"


def test_table_exists_with_rls_forced(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        row = session.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = :t AND relkind = 'r'"
            ),
            {"t": TABLE},
        ).one()
    assert row[0] is True, "RLS ENABLE yok"
    assert row[1] is True, "RLS FORCE yok"


def test_app_role_no_bypassrls(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        row = session.execute(
            text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = 'flowpilot_app'")
        ).one()
    assert row[0] is False
    assert row[1] is False


def test_constraints_and_index_present(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        constraint_sql = text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = (SELECT oid FROM pg_class WHERE relname = :t) "
            "AND contype = :ctype"
        )
        checks = {r[0] for r in session.execute(constraint_sql, {"t": TABLE, "ctype": "c"}).all()}
        uniques = {r[0] for r in session.execute(constraint_sql, {"t": TABLE, "ctype": "u"}).all()}
        indexes = {
            r[0]
            for r in session.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
            ).all()
        }
    assert "ck_purchase_request_requests_amount_positive" in checks
    assert "ck_purchase_request_requests_currency_supported" in checks
    assert "ck_purchase_request_requests_status_valid" in checks
    assert "ix_purchase_request_requests_tenant_status" in indexes
    assert "uq_purchase_request_requests_wf_instance" in uniques


def test_downgrade_then_upgrade_safe(database: DatabaseHandle) -> None:
    cfg = Config(str(REPO_ROOT / "apps" / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "apps" / "backend" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database.migrator_url)
    try:
        command.downgrade(cfg, "0003")
        engine = create_engine(database.migrator_url)
        with engine.connect() as conn:
            remaining = conn.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_name = :t"),
                {"t": TABLE},
            ).scalar_one()
        engine.dispose()
        assert remaining == 0
    finally:
        command.upgrade(cfg, "head")
