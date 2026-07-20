"""organization membership management

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-20

ADDITIVE migration (FP-E03-002, üye yönetimi) — 0001–0008 IMMUTABLE kalır.

organization_memberships tablosunu üye yönetimine hazırlar (rol/status değişimi,
suspend/reactivate/soft-remove, optimistic concurrency):

- `version INTEGER NOT NULL DEFAULT 1` (optimistic CAS) — mevcut satırlar 1'e backfill.
- `updated_at TIMESTAMPTZ NOT NULL` — mevcut satırlar created_at'e backfill.
- UPDATE için tenant-scoped RLS policy (migration 0001 UPDATE grant'i verdi ama policy
  yoktu; FORCE RLS altında policy'siz UPDATE reddediliyordu).
- DELETE grant KALDIRILIR (soft-remove; fiziksel silme yok). 0001 DELETE grant vermişti;
  0009 REVOKE eder. DELETE policy hiç eklenmez.
- Rol/status sorguları için tenant-scoped index'ler (unique (tenant_id, user_id) korunur).

Downgrade forward-only ilkesine tabidir ama test edilebilirlik için sağlanır.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "flowpilot_app"
TABLE = "organization_memberships"


def upgrade() -> None:
    # Expand: nullable ekle → backfill → NOT NULL.
    # version: add_column server_default ile mevcut satırlara 1 uygulanır (UPDATE gerekmez).
    op.add_column(
        TABLE, sa.Column("version", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column(TABLE, sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    # Backfill: FORCE RLS altında migrator (owner) da RLS'e tabidir ve tenant context yok →
    # UPDATE 0 satır etkilerdi. Backfill süresince FORCE'u geçici kaldır (owner bypass eder),
    # sonra geri koy. RLS ENABLE korunur; app rolü (NOBYPASSRLS) etkilenmez.
    op.execute(f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"UPDATE {TABLE} SET updated_at = created_at WHERE updated_at IS NULL")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.alter_column(TABLE, "updated_at", nullable=False)

    # UPDATE RLS policy (tenant-scoped). Metin karşılaştırması: boş/NULL context güvenli red.
    op.execute(
        f"""
        CREATE POLICY membership_scope_update ON {TABLE}
        FOR UPDATE
        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )

    # Soft-remove: fiziksel DELETE YOK. 0001'in verdiği DELETE grant'ı geri al.
    op.execute(f"REVOKE DELETE ON {TABLE} FROM {APP_ROLE}")

    # Rol/status list ve invariant sorguları için tenant-scoped index'ler.
    op.create_index("ix_organization_memberships_tenant_status", TABLE, ["tenant_id", "status"])
    op.create_index(
        "ix_organization_memberships_tenant_role", TABLE, ["tenant_id", "role", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_organization_memberships_tenant_role", table_name=TABLE)
    op.drop_index("ix_organization_memberships_tenant_status", table_name=TABLE)
    op.execute(f"GRANT DELETE ON {TABLE} TO {APP_ROLE}")
    op.execute(f"DROP POLICY IF EXISTS membership_scope_update ON {TABLE}")
    op.drop_column(TABLE, "updated_at")
    op.drop_column(TABLE, "version")
