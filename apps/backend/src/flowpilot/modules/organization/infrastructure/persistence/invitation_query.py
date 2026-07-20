"""`InvitationQuery` adapter'ı — RLS-scoped bekleyen davet listesi (token'sız).

Kendi kısa-ömürlü session'ını açar, tenant context set eder ve YALNIZ current tenant
scope'undaki `pending` + süresi dolmamış davetleri döndürür. token_hash/token
RESPONSE'A GİRMEZ (yalnız güvenli alanlar seçilir).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.organization.application.invitation_dto import PendingInvitationView
from flowpilot.modules.organization.domain.invitation import InvitationStatus
from flowpilot.modules.organization.infrastructure.persistence.tables import invitations_table


class SqlAlchemyInvitationQuery:
    """`InvitationQuery` port'unu uygular (salt-okunur, tenant-scoped)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_pending(
        self, *, tenant_id: UUID, now: datetime, limit: int
    ) -> list[PendingInvitationView]:
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :v, true)"),
                {"v": str(tenant_id)},
            )
            rows = (
                session.execute(
                    select(
                        invitations_table.c.id,
                        invitations_table.c.invited_email,
                        invitations_table.c.role,
                        invitations_table.c.status,
                        invitations_table.c.expires_at,
                        invitations_table.c.invited_by_user_id,
                        invitations_table.c.created_at,
                    )
                    .where(
                        invitations_table.c.tenant_id == tenant_id,
                        invitations_table.c.status == InvitationStatus.PENDING.value,
                        invitations_table.c.expires_at > now,
                    )
                    .order_by(invitations_table.c.created_at.desc(), invitations_table.c.id.desc())
                    .limit(limit)
                )
                .mappings()
                .all()
            )
        return [
            PendingInvitationView(
                invitation_id=row["id"],
                invited_email=str(row["invited_email"]),
                role=str(row["role"]),
                status=str(row["status"]),
                expires_at=row["expires_at"],
                invited_by_user_id=row["invited_by_user_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
