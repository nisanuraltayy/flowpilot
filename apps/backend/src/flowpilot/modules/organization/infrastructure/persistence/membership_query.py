"""`MembershipQuery` adapter'ı — RLS-scoped aktif membership okuması.

Kendi kısa-ömürlü session'ını açar, tenant context'i set eder ve YALNIZ current
tenant scope'undaki aktif üyeliği döndürür (organization_memberships RLS'e tabidir).
Session DIŞARIDAN sessionmaker olarak enjekte edilir; import'ta engine oluşmaz.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.organization.application.contracts import (
    ActiveMembershipView,
    UserOrganizationView,
)
from flowpilot.modules.organization.infrastructure.persistence.tables import (
    memberships_table,
    tenants_table,
)


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

    def list_active_for_user(self, *, user_id: UUID) -> list[UserOrganizationView]:
        # Tek transaction: önce actor context ile kullanıcının AKTİF üyelik satırları
        # (actor-scoped RLS policy — migration 0006), sonra her tenant için org adı
        # mevcut tenant-scope policy ile okunur (tenant context set edilerek).
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_actor_id', :v, true)"),
                {"v": str(user_id)},
            )
            membership_rows = (
                session.execute(
                    select(
                        memberships_table.c.tenant_id,
                        memberships_table.c.role,
                        memberships_table.c.status,
                    ).where(
                        (memberships_table.c.user_id == user_id)
                        & (memberships_table.c.status == "active")
                    )
                )
                .mappings()
                .all()
            )
            organizations: list[UserOrganizationView] = []
            for membership in membership_rows:
                tenant_id = membership["tenant_id"]
                session.execute(
                    text("SELECT set_config('app.current_tenant_id', :v, true)"),
                    {"v": str(tenant_id)},
                )
                name = session.execute(
                    select(tenants_table.c.name).where(tenants_table.c.id == tenant_id)
                ).scalar_one_or_none()
                if name is None:
                    # Tenant kaydı okunamadıysa (beklenmez) org sızdırma — atla.
                    continue
                organizations.append(
                    UserOrganizationView(
                        organization_id=tenant_id,
                        name=str(name),
                        membership_kind=str(membership["role"]),
                        membership_status=str(membership["status"]),
                    )
                )
        return organizations

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
