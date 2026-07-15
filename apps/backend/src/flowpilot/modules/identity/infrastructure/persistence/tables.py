"""Identity — module-owned SQLAlchemy Core tabloları (ADR-009).

`identity_users` GLOBAL bir tablodur (tenant'sız): bir kullanıcı birden fazla
tenant'a üye olabilir (domain-boundaries.md, whitelist). Bu yüzden RLS'e tabi
DEĞİLDİR ve `tenant_id` içermez.

Kimlik eşlemesi: uq(auth_provider, provider_subject) — aynı harici kimlik iki
internal user'a bağlanamaz. PostgreSQL'de NULL'lu satırlar unique'e takılmaz;
bu, auth eşlemesi olmayan eski/test kayıtları için doğru semantiktir.

Bu metadata YALNIZ identity modülüne aittir; başka modül import etmez.
Şema migration 0002 ile eşleşir.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, MetaData, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from flowpilot.shared.db_naming import NAMING_CONVENTION

metadata = MetaData(naming_convention=NAMING_CONVENTION)

users_table = Table(
    "identity_users",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("auth_provider", String(32), nullable=True),
    Column("provider_subject", String(255), nullable=True),
    # Provider'dan gelen SON bilinen e-posta — identity DEĞİL, yalnız gösterim.
    Column("email_snapshot", String(320), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("auth_provider", "provider_subject"),
)
