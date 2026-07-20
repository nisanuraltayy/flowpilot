"""Organization — module-owned SQLAlchemy Core tabloları (ADR-009).

Tenant tabloları RLS'e tabidir (migration'da ENABLE + FORCE + policy).

`organization_tenants.id` bu tablonun kendi tenant kimliğidir — tenant tablosunun
kendisi için `tenant_id` = `id`'dir (FF-03'ün standart tenant-tablosu istisnası).

`organization_memberships.user_id` identity_users'a işaret eder ancak CROSS-MODULE
FK YOKTUR: referential coupling modül ayrılabilirliğini bozar (ADR-003 strangler).
Actor varlığı application katmanında `UserDirectory` ile doğrulanır. Bkz. ASM-0012.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from flowpilot.shared.db_naming import NAMING_CONVENTION

metadata = MetaData(naming_convention=NAMING_CONVENTION)

tenants_table = Table(
    "organization_tenants",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_by_user_id", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

memberships_table = Table(
    "organization_memberships",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "tenant_id",
        UUID(as_uuid=True),
        ForeignKey("organization_tenants.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("user_id", UUID(as_uuid=True), nullable=False),
    Column("role", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    # Aynı kullanıcı aynı tenant içinde iki kez üye olamaz.
    UniqueConstraint("tenant_id", "user_id"),
)

# organization_invitations (tenant-scoped, RLS). `token_hash` YALNIZ SHA-256 hash'tir;
# ham token BU TABLODA TUTULMAZ. `role` DB CHECK ile admin/member ile sınırlıdır (owner
# davetle verilemez). Migration 0007; cross-module identity FK YOK (ASM-0012).
invitations_table = Table(
    "organization_invitations",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "tenant_id",
        UUID(as_uuid=True),
        ForeignKey("organization_tenants.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("invited_email", String(320), nullable=False),
    Column("role", String(32), nullable=False),
    Column("token_hash", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("invited_by_user_id", UUID(as_uuid=True), nullable=False),
    Column("accepted_by_user_id", UUID(as_uuid=True), nullable=True),
    Column("accepted_at", DateTime(timezone=True), nullable=True),
    Column("idempotency_key", String(200), nullable=True),
    Column("request_fingerprint", String(64), nullable=True),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# organization_invitation_accept_idempotency (tenant-scoped, RLS). Davet KABUL
# idempotency'si — create idempotency'sinden AYRI. Ham token/token_hash saklamaz.
# Migration 0008; cross-module identity FK YOK.
invitation_accept_idempotency_table = Table(
    "organization_invitation_accept_idempotency",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "tenant_id",
        UUID(as_uuid=True),
        ForeignKey("organization_tenants.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("actor_user_id", UUID(as_uuid=True), nullable=False),
    Column("idempotency_key", String(200), nullable=False),
    Column("request_fingerprint", String(64), nullable=False),
    Column("invitation_id", UUID(as_uuid=True), nullable=False),
    Column("membership_id", UUID(as_uuid=True), nullable=False),
    Column("response_role", String(32), nullable=False),
    Column("response_status", String(32), nullable=False),
    Column("response_duplicate", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "actor_user_id", "idempotency_key"),
)
