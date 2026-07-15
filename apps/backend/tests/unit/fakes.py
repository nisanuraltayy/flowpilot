"""Unit testleri için deterministik fake'ler (test yardımcıları; pytest toplamaz).

Gerçek adapter yok — clock, id üretimi, repository ve UoW port'ları fake'lenir.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from types import TracebackType
from uuid import UUID

from flowpilot.modules.organization.domain.membership import Membership
from flowpilot.modules.organization.domain.organization import Organization
from flowpilot.shared.identifiers import UserId


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeIdGenerator:
    def __init__(self, uuids: Iterable[UUID]) -> None:
        self._uuids = list(uuids)

    def new_uuid(self) -> UUID:
        return self._uuids.pop(0)


class FakeUserDirectory:
    def __init__(self, existing: Iterable[UUID]) -> None:
        self._existing = {UserId(u) for u in existing}

    def exists(self, user_id: UserId) -> bool:
        return user_id in self._existing


class FakeOrganizationRepository:
    def __init__(self, *, fail_on_tenant: bool = False, fail_on_membership: bool = False) -> None:
        self.tenants: list[Organization] = []
        self.memberships: list[Membership] = []
        self._fail_on_tenant = fail_on_tenant
        self._fail_on_membership = fail_on_membership

    def add_tenant(self, organization: Organization) -> None:
        if self._fail_on_tenant:
            raise RuntimeError("simulated tenant persist failure")
        self.tenants.append(organization)

    def add_membership(self, membership: Membership) -> None:
        if self._fail_on_membership:
            raise RuntimeError("simulated membership persist failure")
        self.memberships.append(membership)


class FakeUnitOfWork:
    def __init__(self, repository: FakeOrganizationRepository) -> None:
        self.organizations = repository
        self.entered = False
        self.committed = False
        self.rolled_back = False
        self.actor_context: UUID | None = None
        self.tenant_context: UUID | None = None

    def __enter__(self) -> FakeUnitOfWork:
        self.entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rolled_back = True

    def set_actor_context(self, actor_user_id: UUID) -> None:
        self.actor_context = actor_user_id

    def set_tenant_context(self, tenant_id: UUID) -> None:
        self.tenant_context = tenant_id

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True
