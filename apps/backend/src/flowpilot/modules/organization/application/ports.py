"""Organization application port'ları.

`OrganizationRepository` aggregate-specific'tir (generic repository YASAK).
`UnitOfWork` tek transaction sınırını ve RLS context ayarını yönetir — business
transaction API/repository içine gömülmez, buradan orkestre edilir.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

from flowpilot.modules.organization.domain.membership import Membership
from flowpilot.modules.organization.domain.organization import Organization


class OrganizationRepository(Protocol):
    """Tenant ve membership yazma port'u (organization modülüne ait tablolar)."""

    def add_tenant(self, organization: Organization) -> None: ...

    def add_membership(self, membership: Membership) -> None: ...


class UnitOfWork(Protocol):
    """Tek transaction + RLS context yönetimi.

    Kullanım:
        with uow:
            uow.set_actor_context(actor)
            uow.organizations.add_tenant(org)
            uow.set_tenant_context(tenant_id)
            uow.organizations.add_membership(membership)
            uow.commit()
    Bir exception oluşursa `__exit__` rollback eder; commit çağrılmaz.
    """

    organizations: OrganizationRepository

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def set_actor_context(self, actor_user_id: UUID) -> None: ...

    def set_tenant_context(self, tenant_id: UUID) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
