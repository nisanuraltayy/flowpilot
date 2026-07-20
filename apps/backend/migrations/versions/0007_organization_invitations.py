"""organization invitations core schema with RLS

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-20

ADDITIVE migration (FP-E03-001, Dilim A — güvenli davet çekirdeği). 0001–0006 IMMUTABLE
kalır, dokunulmaz.

Tek tablo: organization_invitations (organization module-owned).
- `token_hash` YALNIZ SHA-256 hash saklar; ham token ASLA persist edilmez.
- `role` DB CHECK ile 'admin'/'member' ile sınırlıdır — `owner` davetle VERİLEMEZ (ASM-0018).
- `status` ∈ ('pending','accepted','revoked'); `accepted` şema düzeyinde bugünden hazırdır
  ama KABUL AKIŞI bu dilimde YOK (Dilim B).
- Duplicate ön-kontrol: (tenant_id, invited_email) için `status='pending'` partial unique.
- Idempotency: (tenant_id, idempotency_key) partial unique (idempotency_key NOT NULL).
- token lookup için (tenant_id, token_hash) unique index (Dilim B kabul akışına hazır).
- Cross-module identity FK YOKTUR (ASM-0012); tenant FK organization_tenants'a bağlıdır.

Güvenlik: RLS ENABLE + FORCE + tenant policy (SELECT/INSERT/UPDATE). Missing tenant
context → DEFAULT DENY (metin karşılaştırması; boş context güvenli red). flowpilot_app:
SELECT/INSERT/UPDATE (DELETE YOK — davet hard-delete edilmez). migrator: DDL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "flowpilot_app"
TABLE = "organization_invitations"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("invited_email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invited_by_user_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("accepted_by_user_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # owner davetle VERİLEMEZ — DB düzeyinde de zorlanır.
        sa.CheckConstraint(
            "role IN ('admin','member')", name="ck_organization_invitations_role_valid"
        ),
        sa.CheckConstraint(
            "status IN ('pending','accepted','revoked')",
            name="ck_organization_invitations_status_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_invitations"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organization_tenants.id"],
            name="fk_organization_invitations_tenant_id_organization_tenants",
            ondelete="CASCADE",
        ),
    )

    # Liste endpoint'i: tenant_id ile başlayan composite index (database.md §9).
    op.create_index(
        "ix_organization_invitations_tenant_status",
        TABLE,
        ["tenant_id", "status", "created_at"],
    )
    # Token lookup + çakışma direnci (Dilim B kabul akışına hazır): tenant-scoped unique.
    op.create_index(
        "uq_organization_invitations_token_hash",
        TABLE,
        ["tenant_id", "token_hash"],
        unique=True,
    )
    # Aktif bekleyen davet için (tenant_id, invited_email) TEK — duplicate koruması.
    op.execute(
        "CREATE UNIQUE INDEX uq_organization_invitations_pending_email "
        f"ON {TABLE} (tenant_id, invited_email) WHERE status = 'pending'"
    )
    # Idempotency-Key: (tenant_id, idempotency_key) TEK (key NOT NULL olduğunda).
    op.execute(
        "CREATE UNIQUE INDEX uq_organization_invitations_idempotency "
        f"ON {TABLE} (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
    )

    # flowpilot_app: DML (SELECT/INSERT/UPDATE). DELETE YOK — davet hard-delete edilmez.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {TABLE} TO {APP_ROLE}")

    # RLS: enable + force (owner/migrator bypass'ı engelle).
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    # Metin karşılaştırması: boş/NULL context güvenle REDDEDER (0001/0003/0004 deseni).
    # SELECT + INSERT + UPDATE için tenant scope; DELETE policy YOK (hard-delete edilmez).
    op.execute(
        f"""
        CREATE POLICY p_organization_invitations_tenant_select ON {TABLE}
        FOR SELECT
        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )
    op.execute(
        f"""
        CREATE POLICY p_organization_invitations_tenant_insert ON {TABLE}
        FOR INSERT
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )
    op.execute(
        f"""
        CREATE POLICY p_organization_invitations_tenant_update ON {TABLE}
        FOR UPDATE
        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )


def downgrade() -> None:
    # Tabloyu düşürmek policy, grant ve index'leri de kaldırır.
    op.drop_table(TABLE)
