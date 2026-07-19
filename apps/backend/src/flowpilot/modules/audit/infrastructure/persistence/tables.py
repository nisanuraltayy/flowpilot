"""Audit — module-owned SQLAlchemy Core tablosu (append-only, ADR-009).

`audit_entries` tenant-scoped; RLS ENABLE + FORCE (migration 0005). Append-only:
UPDATE/DELETE app rolüne verilmez ve BEFORE UPDATE/DELETE trigger ile de engellenir.
metadata JSONB YALNIZ güvenli, sınırlı alanlar taşır (secret/token/e-posta yok).
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID

from flowpilot.shared.db_naming import NAMING_CONVENTION

metadata = MetaData(naming_convention=NAMING_CONVENTION)

audit_entries_table = Table(
    "audit_entries",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("aggregate_type", String(64), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("actor_user_id", UUID(as_uuid=True), nullable=True),
    Column("role_key", String(64), nullable=True),
    Column("task_id", UUID(as_uuid=True), nullable=True),
    Column("metadata", JSONB, nullable=False, server_default="{}"),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    # Deterministik timeline sırası: aynı occurred_at'te bile insertion order korunur
    # (created → started → task_assigned → ... → completed). Clock'a bağlı değildir.
    Column("seq", BigInteger, Identity(always=True), nullable=False),
    Index("ix_audit_entries_tenant_aggregate", "tenant_id", "aggregate_id", "occurred_at"),
)
