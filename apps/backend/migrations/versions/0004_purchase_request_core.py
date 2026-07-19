"""purchase request core schema with RLS

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-19

ADDITIVE migration (Purchase Request dikey dilimi) — 0001/0002/0003 IMMUTABLE kalır.

Tek tablo: purchase_request_requests (module-owned).
Para minor unit (BIGINT) + currency (CHECK 'TRY'); float YOK. amount_minor > 0.
workflow_instance_id, workflow_runtime instance'ına MANTIKSAL referanstır; CROSS-MODULE
FK YOKTUR (modül ayrılabilirliği — ASM-0012 ile aynı gerekçe). Bağlandığında unique.

Güvenlik: RLS ENABLE + FORCE + tenant policy. Missing tenant context → DEFAULT DENY.
flowpilot_app: DML (SELECT/INSERT/UPDATE), NOSUPERUSER + NOBYPASSRLS. migrator: DDL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "flowpilot_app"
TABLE = "purchase_request_requests"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("workflow_instance_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_purchase_request_requests_amount_positive"),
        sa.CheckConstraint(
            "currency = 'TRY'", name="ck_purchase_request_requests_currency_supported"
        ),
        sa.CheckConstraint(
            "length(btrim(title)) > 0", name="ck_purchase_request_requests_title_not_blank"
        ),
        sa.CheckConstraint(
            "status IN ('draft','in_approval','approved','rejected','cancelled')",
            name="ck_purchase_request_requests_status_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_purchase_request_requests"),
        # NULL'lar Postgres'te distinct → birden çok draft (NULL) çakışmaz;
        # bağlandığında her workflow_instance_id tek talebe bağlıdır.
        sa.UniqueConstraint(
            "workflow_instance_id", name="uq_purchase_request_requests_wf_instance"
        ),
    )
    op.create_index(
        "ix_purchase_request_requests_tenant_status",
        TABLE,
        ["tenant_id", "status", "created_at"],
    )

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {TABLE} TO {APP_ROLE}")

    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    # Metin karşılaştırması: boş/NULL context güvenle REDDEDER (0001/0003 ile aynı desen).
    op.execute(
        f"""
        CREATE POLICY p_purchase_request_tenant_scope ON {TABLE}
        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )


def downgrade() -> None:
    op.drop_table(TABLE)
