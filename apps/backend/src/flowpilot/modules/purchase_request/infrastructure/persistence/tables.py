"""Purchase Request — module-owned SQLAlchemy Core tablosu (ADR-009).

`purchase_request_requests` tenant-scoped; RLS'e tabidir (migration 0004). Para
minor unit (BIGINT) + currency; float YOK. workflow_instance_id, workflow_runtime
modülünün instance'ına MANTIKSAL referanstır ancak CROSS-MODULE FK YOKTUR
(modül ayrılabilirliği — [[ASM-0012]] ile aynı gerekçe).
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from flowpilot.shared.db_naming import NAMING_CONVENTION

metadata = MetaData(naming_convention=NAMING_CONVENTION)

requests_table = Table(
    "purchase_request_requests",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("requested_by_user_id", UUID(as_uuid=True), nullable=False),
    Column("title", String(200), nullable=False),
    Column("description", String(2000), nullable=True),
    Column("amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("status", String(32), nullable=False),
    Column("workflow_instance_id", UUID(as_uuid=True), nullable=True),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("amount_minor > 0", name="amount_positive"),
    CheckConstraint("currency = 'TRY'", name="currency_supported"),
    CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
    CheckConstraint(
        "status IN ('draft','in_approval','approved','rejected','cancelled')",
        name="status_valid",
    ),
    # Bir workflow instance en çok bir talebe bağlanır (bağlıysa unique).
    UniqueConstraint("workflow_instance_id", name="uq_purchase_request_requests_wf_instance"),
    Index("ix_purchase_request_requests_tenant_status", "tenant_id", "status", "created_at"),
)
