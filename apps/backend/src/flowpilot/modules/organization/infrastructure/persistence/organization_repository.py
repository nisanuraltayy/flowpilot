"""SQLAlchemy Core tabanlı OrganizationRepository adapter'ı.

Her `add_*`, INSERT'i hemen `flush()` eder — böylece RLS policy'leri ve
constraint'ler o anda değerlendirilir ve hatalar erken yakalanır. Domain
nesneleri satır sözlüklerine burada map edilir; domain SQLAlchemy bilmez.
"""

from __future__ import annotations

from sqlalchemy import insert
from sqlalchemy.orm import Session

from flowpilot.modules.organization.domain.membership import Membership
from flowpilot.modules.organization.domain.organization import Organization
from flowpilot.modules.organization.infrastructure.persistence.tables import (
    memberships_table,
    tenants_table,
)


class SqlAlchemyOrganizationRepository:
    """`OrganizationRepository` port'unu uygular."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_tenant(self, organization: Organization) -> None:
        self._session.execute(
            insert(tenants_table).values(
                id=organization.id.value,
                name=str(organization.name),
                status=organization.status.value,
                created_by_user_id=organization.created_by.value,
                created_at=organization.created_at,
            )
        )
        self._session.flush()

    def add_membership(self, membership: Membership) -> None:
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
