"""Workflow Runtime — module-owned SQLAlchemy Core tabloları (ADR-009).

Tüm tablolar `workflow_runtime_` önekiyle module ownership'i açıkça gösterir ve
domain-boundaries.md'de workflow_design/work_management/approval/platform'a
planlanan tablolarla ÇAKIŞMAZ (bkz. ASM-0013 — runtime core geçici konsolidasyon).

Tüm tenant tabloları RLS'e tabidir (migration 0003'te ENABLE + FORCE + policy).
Para yoktur (tutar Condition node config'inde minor unit + currency olarak JSONB'de).
Tüm timestamp'ler TIMESTAMPTZ (UTC). Mutable aggregate'lerde `version` (optimistic).
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from flowpilot.shared.db_naming import NAMING_CONVENTION

metadata = MetaData(naming_convention=NAMING_CONVENTION)

# Mantıksal workflow (süreç ailesi).
definitions_table = Table(
    "workflow_runtime_definitions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("definition_key", String(200), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "definition_key"),
)

# Yayınlanmış, IMMUTABLE version (0003'te BEFORE UPDATE/DELETE trigger'ı ile korunur).
definition_versions_table = Table(
    "workflow_runtime_definition_versions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column(
        "definition_id",
        UUID(as_uuid=True),
        ForeignKey("workflow_runtime_definitions.id"),
        nullable=False,
    ),
    Column("version_no", Integer, nullable=False),
    Column("definition", JSONB, nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "definition_id", "version_no"),
)

instances_table = Table(
    "workflow_runtime_instances",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column(
        "definition_version_id",
        UUID(as_uuid=True),
        ForeignKey("workflow_runtime_definition_versions.id"),
        nullable=False,
    ),
    Column("definition_hash", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("current_node_id", String(200), nullable=False),
    Column("context", JSONB, nullable=False, server_default="{}"),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('running','waiting','completed','rejected','cancelled','failed')",
        name="status_valid",
    ),
    Index("ix_workflow_runtime_instances_tenant_status", "tenant_id", "status", "created_at"),
)

tasks_table = Table(
    "workflow_runtime_tasks",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column(
        "instance_id",
        UUID(as_uuid=True),
        ForeignKey("workflow_runtime_instances.id"),
        nullable=False,
    ),
    Column("node_id", String(200), nullable=False),
    Column("step_index", Integer, nullable=False),
    Column("approver_role", String(100), nullable=False),
    Column("assigned_user_id", UUID(as_uuid=True), nullable=True),
    Column("status", String(32), nullable=False),
    Column("decided_by_user_id", UUID(as_uuid=True), nullable=True),
    Column("decision", String(32), nullable=True),
    Column("idempotency_key", String(200), nullable=True),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('pending','active','approved','rejected','changes_requested','cancelled')",
        name="status_valid",
    ),
    # Duplicate task koruması: bir instance'ta bir node'un bir adımı tek kez.
    UniqueConstraint("instance_id", "node_id", "step_index"),
)

# Append-only timeline (0003'te BEFORE UPDATE/DELETE trigger'ı ile korunur).
events_table = Table(
    "workflow_runtime_events",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column(
        "instance_id",
        UUID(as_uuid=True),
        ForeignKey("workflow_runtime_instances.id"),
        nullable=False,
    ),
    Column("event_type", String(100), nullable=False),
    Column("node_id", String(200), nullable=True),
    Column("actor_type", String(32), nullable=False, server_default="system"),
    Column("detail", JSONB, nullable=False, server_default="{}"),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Index("ix_workflow_runtime_events_tenant_instance", "tenant_id", "instance_id", "occurred_at"),
)

# Transactional outbox (ADR-007).
outbox_table = Table(
    "workflow_runtime_outbox",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("event_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", String(100), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("status", String(16), nullable=False, server_default="pending"),
    Column("attempt", Integer, nullable=False, server_default="0"),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("claimed_by", String(100), nullable=True),
    Column("claim_expires_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("processed_at", DateTime(timezone=True), nullable=True),
    CheckConstraint("status IN ('pending','processed','failed')", name="status_valid"),
    UniqueConstraint("event_id"),
    Index("ix_workflow_runtime_outbox_status", "status", "available_at", "id"),
)

# Idempotent inbox (processed events).
inbox_table = Table(
    "workflow_runtime_inbox",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("consumer", String(100), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("processed_at", DateTime(timezone=True), nullable=False),
)

# Persisted timers (in-memory timer YASAK).
timers_table = Table(
    "workflow_runtime_timers",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("instance_id", UUID(as_uuid=True), nullable=False),
    Column("purpose", String(100), nullable=False),
    Column("fire_at", DateTime(timezone=True), nullable=False),
    Column("status", String(16), nullable=False, server_default="pending"),
    Column("fired_at", DateTime(timezone=True), nullable=True),
    Column("fired_by", String(100), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("status IN ('pending','fired','cancelled')", name="status_valid"),
    Index("ix_workflow_runtime_timers_due", "status", "fire_at"),
)

# Tenant-scoped (RLS'e tabi) tablolar — hepsi 'workflow_runtime_' önekli.
TENANT_TABLES: tuple[str, ...] = (
    "workflow_runtime_definitions",
    "workflow_runtime_definition_versions",
    "workflow_runtime_instances",
    "workflow_runtime_tasks",
    "workflow_runtime_events",
    "workflow_runtime_outbox",
    "workflow_runtime_inbox",
    "workflow_runtime_timers",
)
