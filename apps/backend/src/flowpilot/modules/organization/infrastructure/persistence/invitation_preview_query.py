"""`InvitationPreviewQuery` adapter'ı — auth'suz, tenant-scoped davet önizlemesi.

Kendi kısa-ömürlü session'ını açar, tenant context'i (org param'dan) set eder ve token_hash
ile daveti org adına JOIN'leyerek YALNIZ güvenli alanları döndürür. token/token_hash/tam
e-posta RESPONSE'A GİRMEZ. RLS: yanlış tenant + doğru token → satır görünmez.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.organization.application.invitation_ports import InvitationPreviewRow
from flowpilot.modules.organization.infrastructure.persistence.tables import (
    invitations_table,
    tenants_table,
)


class SqlAlchemyInvitationPreviewQuery:
    """`InvitationPreviewQuery` port'unu uygular (salt-okunur, tenant-scoped)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def find(self, *, tenant_id: UUID, token_hash: str) -> InvitationPreviewRow | None:
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :v, true)"),
                {"v": str(tenant_id)},
            )
            row = (
                session.execute(
                    select(
                        invitations_table.c.tenant_id,
                        invitations_table.c.role,
                        invitations_table.c.status,
                        invitations_table.c.expires_at,
                        tenants_table.c.name.label("organization_name"),
                    )
                    .select_from(
                        invitations_table.join(
                            tenants_table, tenants_table.c.id == invitations_table.c.tenant_id
                        )
                    )
                    .where(
                        invitations_table.c.tenant_id == tenant_id,
                        invitations_table.c.token_hash == token_hash,
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return InvitationPreviewRow(
            organization_id=row["tenant_id"],
            organization_name=str(row["organization_name"]),
            role=str(row["role"]),
            status=str(row["status"]),
            expires_at=row["expires_at"],
        )
