"""0007 migration — tablo/constraint/index/RLS/policy + 0006→0007 upgrade doğrulaması.

Fresh 0001→0007 yükseltmesi session fixture'ı tarafından (boş container → head) zaten
uygulanır; bu testler yapıyı ve 0006→0007 yolunu doğrular.
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration._support import REPO_ROOT
from tests.integration.conftest import DatabaseHandle

TABLE = "organization_invitations"


def _alembic_config(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "apps" / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "apps" / "backend" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


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


def test_constraints_and_indexes_present(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        checks = {
            r[0]
            for r in session.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = (SELECT oid FROM pg_class WHERE relname = :t) "
                    "AND contype = 'c'"
                ),
                {"t": TABLE},
            ).all()
        }
        indexes = {
            r[0]
            for r in session.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
            ).all()
        }
    assert "ck_organization_invitations_role_valid" in checks
    assert "ck_organization_invitations_status_valid" in checks
    assert "ix_organization_invitations_tenant_status" in indexes
    assert "uq_organization_invitations_token_hash" in indexes
    assert "uq_organization_invitations_pending_email" in indexes
    assert "uq_organization_invitations_idempotency" in indexes


def test_status_check_accepts_expired(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        definition = session.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_organization_invitations_status_valid'"
            )
        ).scalar_one()
    for value in ("pending", "accepted", "revoked", "expired"):
        assert value in definition, f"status CHECK '{value}' değerini kabul etmiyor"


def test_rls_policies_present(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        policies = {
            r[0]
            for r in session.execute(
                text("SELECT policyname FROM pg_policies WHERE tablename = :t"), {"t": TABLE}
            ).all()
        }
    assert "p_organization_invitations_tenant_select" in policies
    assert "p_organization_invitations_tenant_insert" in policies
    assert "p_organization_invitations_tenant_update" in policies


def test_app_role_grants_no_delete(app_sessionmaker: sessionmaker[Session]) -> None:
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
    assert "DELETE" not in privileges  # davet hard-delete edilmez


def test_downgrade_to_0006_then_upgrade_head(database: DatabaseHandle) -> None:
    cfg = _alembic_config(database.migrator_url)
    try:
        command.downgrade(cfg, "0006")
        engine = create_engine(database.migrator_url)
        with engine.connect() as conn:
            remaining = conn.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_name = :t"),
                {"t": TABLE},
            ).scalar_one()
        engine.dispose()
        assert remaining == 0, "0006'ya downgrade tabloyu kaldırmadı"
    finally:
        command.upgrade(cfg, "head")
    # Head'e tekrar yükseltince tablo geri gelir (0006 → 0007 upgrade yolu).
    engine = create_engine(database.migrator_url)
    with engine.connect() as conn:
        restored = conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_name = :t"),
            {"t": TABLE},
        ).scalar_one()
    engine.dispose()
    assert restored == 1
