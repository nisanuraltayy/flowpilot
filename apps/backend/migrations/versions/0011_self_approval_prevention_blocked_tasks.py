"""self approval prevention and blocked approval tasks

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-21

ADDITIVE migration (FP-E06-009, self-approval engelleme) — 0001–0010 IMMUTABLE kalır.

workflow_runtime_tasks'i "blocked" (uygun onaycı yok — ör. çözülen assignee talep sahibi)
adımlarını temsil edecek şekilde genişletir:

- status CHECK'e `blocked` eklenir (NON-terminal; yalnız güvenli resolve ile active olur).
- `blocked_reason` (nullable, küçük değer seti CHECK'i) — şimdilik yalnız
  `self_approval_no_eligible_assignee`.
- `blocked_at` (nullable TIMESTAMPTZ) — bloklama zamanı (görünürlük/audit).
- (tenant_id, status) index'i — blocked-task listeleme sorgusu için.

Eski task verileri KORUNUR: mevcut pending/active/approved/rejected/changes_requested/
cancelled satırlar dokunulmaz. Yeni status yalnız yeni akışlarda üretilir. RLS ENABLE+FORCE
ve tenant policy 0003'ten gelir (değişmez); DELETE grant/policy EKLENMEZ.

Instance/purchase_request status'una yeni değer EKLENMEZ: blocked task-seviyesindedir;
instance running/waiting, purchase request in_approval kalır. API/read model blocked'ı
açıkça gösterir.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "workflow_runtime_tasks"
STATUS_CK = "ck_workflow_runtime_tasks_status_valid"
REASON_CK = "ck_workflow_runtime_tasks_blocked_reason_valid"
_OLD_STATUSES = "'pending','active','approved','rejected','changes_requested','cancelled'"
_NEW_STATUSES = (
    "'pending','active','blocked','approved','rejected','changes_requested','cancelled'"
)


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("blocked_reason", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))

    # status CHECK'i 'blocked' içerecek şekilde genişlet (drop + recreate).
    op.drop_constraint(STATUS_CK, TABLE, type_="check")
    op.create_check_constraint(STATUS_CK, TABLE, f"status IN ({_NEW_STATUSES})")

    # blocked_reason küçük, kontrol edilebilir değer seti (yalnız self-approval kaynağı).
    op.create_check_constraint(
        REASON_CK,
        TABLE,
        "blocked_reason IS NULL OR blocked_reason IN ('self_approval_no_eligible_assignee')",
    )

    op.create_index("ix_workflow_runtime_tasks_tenant_status", TABLE, ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_workflow_runtime_tasks_tenant_status", table_name=TABLE)
    op.drop_constraint(REASON_CK, TABLE, type_="check")
    # 'blocked' satır varsa eski CHECK'e dönüş başarısız olur (forward-only ilke); test
    # ortamında boş/normal veri ile downgrade doğrulanır.
    op.drop_constraint(STATUS_CK, TABLE, type_="check")
    op.create_check_constraint(STATUS_CK, TABLE, f"status IN ({_OLD_STATUSES})")
    op.drop_column(TABLE, "blocked_at")
    op.drop_column(TABLE, "blocked_reason")
