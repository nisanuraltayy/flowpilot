"""actor-scoped membership SELECT policy (self memberships across tenants)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-19

ADDITIVE + owner-approved migration — 0001–0005 IMMUTABLE kalır.

Amaç: `GET /v1/me/organizations` — bir kullanıcının HANGİ organizasyonlara üye
olduğunu (yeniden girişte, aktif org context'i çözmek için) listeleyebilmesi.

`organization_memberships` üzerindeki tek SELECT policy tenant-scoped'tur
(`tenant_id = current_tenant_id`; migration 0001). flowpilot_app NOBYPASSRLS
olduğundan cross-tenant "kendi üyeliklerim" listesi mevcut policy ile ALINAMAZ.

Bu migration ADDITIVE, güvenlik-KORUYAN ikinci bir SELECT policy ekler: kullanıcı
YALNIZ KENDİ üyelik satırlarını görebilir (`user_id = current_actor_id`). RLS
policy'leri OR ile birleşir; yani mevcut tenant-scope davranışı DEĞİŞMEZ, yalnız
actor kendi satırlarını da görebilir hâle gelir. Başka kullanıcının üyeliği veya
başka tenant'ın verisi SIZMAZ. Org ADI, actor'ın üye olduğu her tenant için mevcut
tenant-scope policy ile (tenant context set edilerek) okunur — yeni tenant policy
GEREKMEZ.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Metin karşılaştırması: boş/NULL context (reset sonrası '') güvenle REDDEDİLİR
    # (migration 0001'deki gerekçeyle tutarlı) — hata üretmez, eşleşme olmaz.
    op.execute(
        """
        CREATE POLICY membership_actor_select ON organization_memberships
        FOR SELECT
        USING (user_id::text = current_setting('app.current_actor_id', true))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS membership_actor_select ON organization_memberships")
