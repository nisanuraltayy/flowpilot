"""initial identity and organization schema with RLS

Revision ID: 0001
Revises:
Create Date: 2026-07-15

İlk migration — YALNIZ organization creation use-case'inin ihtiyaç duyduğu üç
tablo, constraint'ler, grant'lar ve tenant tabloları için RLS.

Roller (provision_local_database.py / test fixture tarafından ÖNCEDEN oluşturulur):
  - flowpilot_migrator : bu migration'ı çalıştırır, tabloların sahibidir (DDL).
  - flowpilot_app      : uygulamanın DML rolü; NOSUPERUSER, NOBYPASSRLS.

RLS:
  - organization_tenants ve organization_memberships: ENABLE + FORCE ROW LEVEL
    SECURITY. FORCE, tablo sahibinin (migrator) da RLS'e tabi olmasını sağlar —
    böylece owner üzerinden sessiz bypass engellenir.
  - identity_users GLOBAL tablodur (RLS yok): bir kullanıcı birden fazla tenant'a
    üye olabilir.
  - Transaction-local context: app.current_actor_id, app.current_tenant_id
    (set_config(..., true)). Context yoksa erişim DEFAULT DENY'dir.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "flowpilot_app"


def upgrade() -> None:
    # --- identity_users (GLOBAL — RLS yok) ---
    op.create_table(
        "identity_users",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("external_auth_subject", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_identity_users"),
        sa.UniqueConstraint(
            "external_auth_subject", name="uq_identity_users_external_auth_subject"
        ),
    )

    # --- organization_tenants (tenant tablosu; id = tenant kimliği) ---
    op.create_table(
        "organization_tenants",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organization_tenants"),
    )

    # --- organization_memberships (tenant-scoped) ---
    op.create_table(
        "organization_memberships",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("user_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organization_memberships"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization_tenants.id"],
            name="fk_organization_memberships_tenant_id_organization_tenants",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "user_id", name="uq_organization_memberships_tenant_id"
        ),
    )

    # --- Grant'lar: app rolü yalnız DML (DDL yok) ---
    for table in ("identity_users", "organization_tenants", "organization_memberships"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")

    # --- RLS: enable + force (owner bypass'ı engelle) ---
    for table in ("organization_tenants", "organization_memberships"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # --- Policy'ler ---
    # NOT: karşılaştırma METİN üzerinden yapılır (id::text = current_setting(...)).
    # Gerekçe: transaction-local set_config reset edildiğinde custom GUC BOŞ STRING
    # ''e döner; ''::uuid "invalid input syntax" hatası verir. Metin karşılaştırması
    # boş/NULL context'i güvenle REDDEDER (eşleşme olmaz), hata üretmez.
    #
    # Tenant SELECT: yalnız current tenant scope'u görülebilir.
    op.execute(
        """
        CREATE POLICY tenant_scope_select ON organization_tenants
        FOR SELECT
        USING (id::text = current_setting('app.current_tenant_id', true))
        """
    )
    # Tenant INSERT: yalnız current actor KENDİ adına organizasyon oluşturabilir.
    op.execute(
        """
        CREATE POLICY tenant_actor_insert ON organization_tenants
        FOR INSERT
        WITH CHECK (
            created_by_user_id::text = current_setting('app.current_actor_id', true)
        )
        """
    )
    # Membership SELECT: yalnız current tenant scope'undaki üyelikler görülebilir.
    op.execute(
        """
        CREATE POLICY membership_scope_select ON organization_memberships
        FOR SELECT
        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )
    # Membership INSERT: yalnız current tenant scope'una üyelik eklenebilir.
    op.execute(
        """
        CREATE POLICY membership_scope_insert ON organization_memberships
        FOR INSERT
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )


def downgrade() -> None:
    # Tabloları düşürmek policy ve grant'ları da kaldırır. Ters sırada.
    op.drop_table("organization_memberships")
    op.drop_table("organization_tenants")
    op.drop_table("identity_users")
