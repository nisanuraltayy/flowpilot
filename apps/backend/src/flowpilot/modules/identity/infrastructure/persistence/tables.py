"""Identity — module-owned SQLAlchemy Core tabloları (ADR-009).

`identity_users` GLOBAL bir tablodur (tenant'sız): bir kullanıcı birden fazla
tenant'a üye olabilir (domain-boundaries.md, whitelist). Bu yüzden RLS'e tabi
DEĞİLDİR ve `tenant_id` içermez.

Bu metadata YALNIZ identity modülüne aittir; başka modül import etmez.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, MetaData, String, Table
from sqlalchemy.dialects.postgresql import UUID

from flowpilot.shared.db_naming import NAMING_CONVENTION

metadata = MetaData(naming_convention=NAMING_CONVENTION)

users_table = Table(
    "identity_users",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("email", String(320), nullable=False),
    Column("external_auth_subject", String(255), nullable=True, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
