"""0009 migration — üye yönetimi kolonları/policy/grant/index + backfill + downgrade.

Fresh 0001→0009 yükseltmesi session fixture'ı tarafından (boş container → head) zaten
uygulanır; bu testler 0009'un eklediği yapıyı, backfill'i ve 0009→0008→head yolunu doğrular.
0001–0008 IMMUTABLE kalır; bu dosya yalnız 0009'u kapsar.
"""

from __future__ import annotations

from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration._support import REPO_ROOT
from tests.integration.conftest import DatabaseHandle

TABLE = "organization_memberships"


def _alembic_config(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "apps" / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "apps" / "backend" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_single_head_advanced_past_0009(database: DatabaseHandle) -> None:
    # 0009 artık head DEĞİL (0010 tarafından revise edildi); tek head 0010'dur. Bu test
    # yalnız "tek head var ve zincir 0009'un ötesine ilerledi" invariant'ını doğrular.
    engine = create_engine(database.migrator_url)
    with engine.connect() as conn:
        heads = {r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version")).all()}
    engine.dispose()
    assert heads == {"0010"}, f"beklenen tek head 0010, bulunan: {heads}"


def test_version_and_updated_at_columns(app_sessionmaker: sessionmaker[Session]) -> None:
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
    assert "updated_at" in cols and cols["updated_at"][1] == "NO"  # NOT NULL


def test_update_policy_present(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        policies = {
            r[0]: r[1]
            for r in session.execute(
                text("SELECT policyname, cmd FROM pg_policies WHERE tablename = :t"), {"t": TABLE}
            ).all()
        }
    assert "membership_scope_update" in policies
    assert policies["membership_scope_update"] == "UPDATE"
    # Soft-remove: DELETE policy'si HİÇ yok.
    assert all(cmd != "DELETE" for cmd in policies.values())


def test_grants_update_yes_delete_no(app_sessionmaker: sessionmaker[Session]) -> None:
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
    assert "DELETE" not in privileges  # 0009 REVOKE etti (soft-remove)


def test_tenant_scoped_indexes_present(app_sessionmaker: sessionmaker[Session]) -> None:
    with app_sessionmaker() as session:
        indexes = {
            r[0]
            for r in session.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
            ).all()
        }
    assert "ix_organization_memberships_tenant_status" in indexes
    assert "ix_organization_memberships_tenant_role" in indexes
    # Mevcut unique (tenant_id, user_id) korunur.
    assert "uq_organization_memberships_tenant_id" in indexes


def test_backfill_sets_version_one_and_updated_at_from_created_at(
    database: DatabaseHandle,
) -> None:
    """0008 şemasında satır ekle → 0009'a yükselt → version=1, updated_at=created_at."""
    cfg = _alembic_config(database.migrator_url)
    tenant_id = uuid4()
    actor_id = uuid4()
    membership_id = uuid4()
    try:
        command.downgrade(cfg, "0008")
        engine = create_engine(database.migrator_url)
        with engine.begin() as conn:
            # 0008'de version/updated_at YOK; RLS policy'lerine uyarak (tenant/actor context) ekle.
            conn.execute(
                text("SELECT set_config('app.current_actor_id', :a, true)"), {"a": str(actor_id)}
            )
            conn.execute(
                text(
                    "INSERT INTO organization_tenants (id, name, status, created_by_user_id, "
                    "created_at) VALUES (:id, 'Backfill Org', 'active', :actor, now())"
                ),
                {"id": str(tenant_id), "actor": str(actor_id)},
            )
            conn.execute(
                text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
            conn.execute(
                text(
                    "INSERT INTO organization_memberships (id, tenant_id, user_id, role, status, "
                    "created_at) VALUES (:id, :t, :u, 'owner', 'active', "
                    "timestamptz '2026-01-01 00:00:00+00')"
                ),
                {"id": str(membership_id), "t": str(tenant_id), "u": str(actor_id)},
            )
        engine.dispose()
    finally:
        command.upgrade(cfg, "head")

    engine = create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE organization_memberships NO FORCE ROW LEVEL SECURITY"))
        row = conn.execute(
            text(
                "SELECT version, updated_at, created_at FROM organization_memberships WHERE id = :i"
            ),
            {"i": str(membership_id)},
        ).one()
        conn.execute(text("ALTER TABLE organization_memberships FORCE ROW LEVEL SECURITY"))
    engine.dispose()
    assert row[0] == 1, "version 1'e backfill edilmedi"
    assert row[1] == row[2], "updated_at created_at'e backfill edilmedi"


def test_downgrade_to_0008_removes_columns_then_upgrade_head(database: DatabaseHandle) -> None:
    cfg = _alembic_config(database.migrator_url)
    try:
        command.downgrade(cfg, "0008")
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
            policies = {
                r[0]
                for r in conn.execute(
                    text("SELECT policyname FROM pg_policies WHERE tablename = :t"), {"t": TABLE}
                ).all()
            }
            delete_grant = conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.role_table_grants "
                    "WHERE table_name = :t AND grantee = 'flowpilot_app' "
                    "AND privilege_type = 'DELETE'"
                ),
                {"t": TABLE},
            ).scalar_one()
        engine.dispose()
        assert "version" not in cols and "updated_at" not in cols
        assert "membership_scope_update" not in policies
        assert delete_grant == 1, "0008'e downgrade DELETE grant'ı geri vermedi"
    finally:
        command.upgrade(cfg, "head")
    # head'e geri yükselt: kolonlar tekrar var (0008 → 0009 upgrade yolu).
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
    assert "version" in cols and "updated_at" in cols
