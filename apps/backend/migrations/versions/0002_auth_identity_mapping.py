"""auth identity mapping

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-15

identity_users tablosunu harici kimlik eşlemesine hazırlar (0001 DEĞİŞTİRİLMEDİ):

- external_auth_subject -> provider_subject (rename; veri korunur)
- email -> email_snapshot (rename + NULLABLE; e-posta identity DEĞİLDİR,
  yalnız provider'dan gelen son bilinen değerdir)
- auth_provider kolonu eklenir (nullable — eşlemesi olmayan eski kayıtlar için)
- uq(auth_provider, provider_subject): aynı harici kimlik iki internal user'a
  bağlanamaz. Concurrent EnsureAuthenticatedUser yarışının GERÇEK koruması
  bu constraint'tir (application-level exists kontrolü değil).

Rename'ler additive-güvenlidir (veri kaybı yok) ve henüz deploy edilmiş
tüketici olmadığı için expand/contract gerektirmez.

Downgrade notu: email kolonunu NOT NULL'a geri döndürmek için NULL snapshot'lar
placeholder ile doldurulur (yalnız boş/test DB'lerde çalıştırılması beklenir);
veri SİLİNMEZ.

Supabase password, refresh token veya session verisi SAKLANMAZ (ADR-005).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_identity_users_external_auth_subject", "identity_users", type_="unique"
    )
    op.alter_column(
        "identity_users",
        "external_auth_subject",
        new_column_name="provider_subject",
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "identity_users",
        "email",
        new_column_name="email_snapshot",
        existing_type=sa.String(length=320),
        nullable=True,
    )
    op.add_column(
        "identity_users",
        sa.Column("auth_provider", sa.String(length=32), nullable=True),
    )
    op.create_unique_constraint(
        "uq_identity_users_auth_provider",
        "identity_users",
        ["auth_provider", "provider_subject"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_identity_users_auth_provider", "identity_users", type_="unique")
    op.drop_column("identity_users", "auth_provider")
    # NOT NULL'a dönmeden önce NULL snapshot'lar placeholder ile doldurulur
    # (veri silinmez; yalnız boş/test DB'lerde beklenen bir yol).
    op.execute(
        "UPDATE identity_users SET email_snapshot = 'unknown@invalid.local' "
        "WHERE email_snapshot IS NULL"
    )
    op.alter_column(
        "identity_users",
        "email_snapshot",
        new_column_name="email",
        existing_type=sa.String(length=320),
        nullable=False,
    )
    op.alter_column(
        "identity_users",
        "provider_subject",
        new_column_name="external_auth_subject",
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
    op.create_unique_constraint(
        "uq_identity_users_external_auth_subject",
        "identity_users",
        ["external_auth_subject"],
    )
