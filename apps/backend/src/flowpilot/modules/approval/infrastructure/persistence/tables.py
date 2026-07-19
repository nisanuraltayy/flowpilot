"""Approval — module-owned SQLAlchemy Core tabloları (ADR-009).

`approval_role_assignments`: tenant + role_key için TEK aktif assignee (partial unique
index WHERE status='active', migration 0005). `approval_decisions`: append-only; task
başına tek terminal karar (unique task_id) + tenant/idempotency_key unique. Tenant tabloları
RLS'e tabidir. Cross-module FK YOK ([[ASM-0012]] gerekçesi).
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from flowpilot.shared.db_naming import NAMING_CONVENTION

metadata = MetaData(naming_convention=NAMING_CONVENTION)

role_assignments_table = Table(
    "approval_role_assignments",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("role_key", String(64), nullable=False),
    Column("assigned_user_id", UUID(as_uuid=True), nullable=False),
    Column("status", String(16), nullable=False, server_default="active"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_approval_role_assignments_tenant", "tenant_id", "role_key"),
    # Partial unique (tek aktif assignee) migration 0005'te CREATE UNIQUE INDEX ... WHERE.
)

decisions_table = Table(
    "approval_decisions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("task_id", UUID(as_uuid=True), nullable=False),
    Column("actor_user_id", UUID(as_uuid=True), nullable=False),
    Column("decision", String(16), nullable=False),
    Column("comment", String(2000), nullable=True),
    Column("idempotency_key", String(200), nullable=False),
    Column("request_fingerprint", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("task_id", name="uq_approval_decisions_task_id"),
    UniqueConstraint("tenant_id", "idempotency_key", name="uq_approval_decisions_tenant_id"),
)
