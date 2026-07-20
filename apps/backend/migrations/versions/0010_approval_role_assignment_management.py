"""approval role assignment management

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-21

ADDITIVE migration (FP-E10-004, gerçek kullanıcılara onay rolü atama) — 0001–0009 IMMUTABLE.

approval_role_assignments tablosunu owner/admin tarafından yönetilen (reassign) atamalara
hazırlar. Mevcut yapı KORUNUR:
- `updated_at TIMESTAMPTZ NOT NULL` ZATEN VAR (0005) — tekrar eklenmez.
- Tenant RLS policy `p_approval_role_assignments_tenant_scope` (0005) FOR ALL'dur (USING +
  WITH CHECK, komut kısıtı yok) → UPDATE'i ZATEN kapsar. Ayrı UPDATE policy'si GEREKMEZ.
- UPDATE grant ZATEN verildi (0005: SELECT, INSERT, UPDATE). DELETE grant HİÇ verilmedi.
- Partial unique `uq_approval_role_assignments_active` (tenant_id, role_key WHERE active)
  KORUNUR — reassign eski satırı revoked yapıp yeni active ekler; her an tek active.

Bu migration YALNIZ şunu ekler:
- `version INTEGER NOT NULL DEFAULT 1` (optimistic CAS) — mevcut satırlar 1'e backfill.
- Rol/kullanıcı sorguları için tenant-scoped index'ler.
- Soft-delete garanti için DELETE grant'ı açıkça REVOKE (idempotent; zaten yoktu).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "flowpilot_app"
TABLE = "approval_role_assignments"


def upgrade() -> None:
    # version: server_default ile mevcut satırlar 1'e backfill edilir (UPDATE gerekmez).
    op.add_column(
        TABLE, sa.Column("version", sa.Integer(), server_default="1", nullable=False)
    )

    # Soft-delete: fiziksel DELETE YOK. 0005 DELETE grant vermedi; yine de açıkça REVOKE
    # ederek niyeti sabitle (idempotent — hak yoksa no-op).
    op.execute(f"REVOKE DELETE ON {TABLE} FROM {APP_ROLE}")

    # Reassign/list ve invariant sorguları için tenant-scoped index'ler
    # (mevcut ix_approval_role_assignments_tenant (tenant_id, role_key) korunur).
    op.create_index(
        "ix_approval_role_assignments_tenant_role_status",
        TABLE,
        ["tenant_id", "role_key", "status"],
    )
    op.create_index(
        "ix_approval_role_assignments_tenant_user_status",
        TABLE,
        ["tenant_id", "assigned_user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_approval_role_assignments_tenant_user_status", table_name=TABLE)
    op.drop_index("ix_approval_role_assignments_tenant_role_status", table_name=TABLE)
    op.drop_column(TABLE, "version")
