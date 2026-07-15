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
    Column,
    DateTime,
    ForeignKey,
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
