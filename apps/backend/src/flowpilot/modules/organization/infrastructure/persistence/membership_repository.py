"""Session-tabanlı `MembershipWriteRepository` adapter'ı (davet kabul akışı).

Kabul transaction'ının parçası olarak AYNI session üzerinde çalışır: üyelik ekler ve
(herhangi status) üyelik okur. Tenant context çağıran UoW tarafından set edilir (RLS).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from flowpilot.modules.organization.application.invitation_ports import MembershipRecord
from flowpilot.modules.organization.domain.membership import Membership
from flowpilot.modules.organization.infrastructure.persistence.tables import memberships_table


class SqlAlchemyMembershipWriteRepository:
    """`MembershipWriteRepository` port'unu uygular (kabul akışı)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, membership: Membership) -> None:
        # unique(tenant_id, user_id): eşzamanlı ikinci kabul burada IntegrityError alır.
        self._session.execute(
            insert(memberships_table).values(
                id=membership.id.value,
                tenant_id=membership.tenant_id.value,
                user_id=membership.user_id.value,
                role=membership.role.value,
                status=membership.status.value,
                created_at=membership.created_at,
            )
        )
        self._session.flush()

    def find_by_user(self, *, tenant_id: UUID, user_id: UUID) -> MembershipRecord | None:
        row = self._session.execute(
            select(
                memberships_table.c.id,
                memberships_table.c.role,
                memberships_table.c.status,
            ).where(
                memberships_table.c.tenant_id == tenant_id,
                memberships_table.c.user_id == user_id,
            )
        ).first()
        if row is None:
            return None
        return MembershipRecord(membership_id=row.id, role=str(row.role), status=str(row.status))
