"""invitation acceptance idempotency

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-20

ADDITIVE migration (FP-E03-001, Dilim B idempotency) — 0001–0007 IMMUTABLE kalır.

Tek tablo: organization_invitation_accept_idempotency (organization module-owned).
POST /v1/invitations/accept için Idempotency-Key desteği: aynı actor + org + key + payload
replay'inde önceki sonuç döner; aynı key farklı payload/org → conflict.

- Bu tablo davet OLUŞTURMA idempotency'sinden (organization_invitations.idempotency_key)
  BAĞIMSIZDIR; iki operasyonun idempotency kayıtları karışmaz.
- request_fingerprint = hash(operation | organization_id | token_hash); ham token veya
  token_hash DOĞRUDAN saklanmaz (yalnız fingerprint hash'i içinde).
- Unique (tenant_id, actor_user_id, idempotency_key): aynı key yarışında tek kazanan.
- RLS: tenant-scoped SELECT/INSERT + actor-scoped SELECT (kullanıcı KENDİ kayıtlarını
  cross-tenant görür — migration 0006 deseni). Actor-scoped read, "aynı key farklı org →
  409" tespiti içindir; başka kullanıcının/başka tenant'ın kaydı SIZMAZ.
- Grant: SELECT + INSERT (append-only; UPDATE/DELETE YOK). Cross-module identity FK YOK.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "flowpilot_app"
TABLE = "organization_invitation_accept_idempotency"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("invitation_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("response_role", sa.String(length=32), nullable=False),
        sa.Column("response_status", sa.String(length=32), nullable=False),
        sa.Column("response_duplicate", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organization_invitation_accept_idempotency"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization_tenants.id"],
            name="fk_org_invitation_accept_idem_tenant_id_organization_tenants",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "actor_user_id",
            "idempotency_key",
            name="uq_org_invitation_accept_idem_scope",
        ),
    )
    # Actor-scoped lookup (find_for_actor): (actor_user_id, idempotency_key).
    op.create_index(
        "ix_org_invitation_accept_idem_actor_key",
        TABLE,
        ["actor_user_id", "idempotency_key"],
    )

    # Append-only: SELECT + INSERT (UPDATE/DELETE YOK).
    op.execute(f"GRANT SELECT, INSERT ON {TABLE} TO {APP_ROLE}")

    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    # Metin karşılaştırması: boş/NULL context güvenle REDDEDER (0001/0006/0007 deseni).
    # Tenant-scoped SELECT.
    op.execute(
        f"""
        CREATE POLICY p_org_invitation_accept_idem_tenant_select ON {TABLE}
        FOR SELECT
        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )
    # Actor-scoped SELECT: kullanıcı KENDİ kayıtlarını cross-tenant görür (cross-org 409
    # tespiti için; migration 0006 deseni). Policy'ler OR ile birleşir. Başka kullanıcının
    # veya başka tenant'ın (farklı actor) kaydı SIZMAZ.
    op.execute(
        f"""
        CREATE POLICY p_org_invitation_accept_idem_actor_select ON {TABLE}
        FOR SELECT
        USING (actor_user_id::text = current_setting('app.current_actor_id', true))
        """
    )
    # Tenant-scoped INSERT: kayıt yalnız current tenant scope'una eklenir.
    op.execute(
        f"""
        CREATE POLICY p_org_invitation_accept_idem_tenant_insert ON {TABLE}
        FOR INSERT
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )


def downgrade() -> None:
    op.drop_table(TABLE)
