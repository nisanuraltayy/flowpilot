"""`MembershipQuery` adapter'ı — RLS-scoped aktif membership okuması.

Kendi kısa-ömürlü session'ını açar, tenant context'i set eder ve YALNIZ current
tenant scope'undaki aktif üyeliği döndürür (organization_memberships RLS'e tabidir).
Session DIŞARIDAN sessionmaker olarak enjekte edilir; import'ta engine oluşmaz.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.organization.application.contracts import ActiveMembershipView
from flowpilot.modules.organization.infrastructure.persistence.tables import memberships_table


class SqlAlchemyMembershipQuery:
    """`MembershipQuery` port'unu uygular."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def find_active(self, *, tenant_id: UUID, user_id: UUID) -> ActiveMembershipView | None:
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :v, true)"),
                {"v": str(tenant_id)},
            )
            row = (
                session.execute(
                    select(
                        memberships_table.c.id,
                        memberships_table.c.tenant_id,
                        memberships_table.c.user_id,
                        memberships_table.c.role,
                    ).where(
                        (memberships_table.c.tenant_id == tenant_id)
                        & (memberships_table.c.user_id == user_id)
                        & (memberships_table.c.status == "active")
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return ActiveMembershipView(
            membership_id=row["id"],
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            role=str(row["role"]),
        )

    def find_active_owner(self, *, tenant_id: UUID) -> ActiveMembershipView | None:
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :v, true)"),
                {"v": str(tenant_id)},
            )
            row = (
                session.execute(
                    select(
                        memberships_table.c.id,
                        memberships_table.c.tenant_id,
                        memberships_table.c.user_id,
                        memberships_table.c.role,
                    )
                    .where(
                        (memberships_table.c.tenant_id == tenant_id)
                        & (memberships_table.c.role == "owner")
                        & (memberships_table.c.status == "active")
                    )
                    .order_by(memberships_table.c.created_at)
                    .limit(1)
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return ActiveMembershipView(
            membership_id=row["id"],
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            role=str(row["role"]),
        )
