"""Üye yönetimi use-case testleri için deterministik fake'ler (pytest toplamaz)."""

from __future__ import annotations

from dataclasses import replace
from types import TracebackType
from uuid import UUID

from flowpilot.modules.audit.application.dto import AuditRecord
from flowpilot.modules.organization.application.member_dto import MemberView
from flowpilot.modules.organization.application.member_errors import MembershipConcurrencyError
from flowpilot.modules.organization.domain.membership import (
    Membership,
    MembershipRole,
    MembershipStatus,
)


class FakeMemberListQuery:
    def __init__(self, views: list[MemberView] | None = None) -> None:
        self.views = views or []
        self.calls: list[tuple[UUID, int]] = []

    def list_members(self, *, tenant_id: UUID, limit: int) -> list[MemberView]:
        self.calls.append((tenant_id, limit))
        return self.views[:limit]


class FakeMembershipManagementRepository:
    """(tenant, user) -> Membership; FOR UPDATE ve CAS'ı taklit eder."""

    def __init__(self, seed: dict[tuple[UUID, UUID], Membership] | None = None) -> None:
        self.store: dict[tuple[UUID, UUID], Membership] = dict(seed) if seed else {}
        self.updated: list[Membership] = []
        self.tenant_locks: list[UUID] = []

    def acquire_tenant_lock(self, *, tenant_id: UUID) -> None:
        self.tenant_locks.append(tenant_id)

    def find_by_user_for_update(self, *, tenant_id: UUID, user_id: UUID) -> Membership | None:
        return self.store.get((tenant_id, user_id))

    def count_active_owners_for_update(self, *, tenant_id: UUID) -> int:
        return sum(
            1
            for (tid, _), m in self.store.items()
            if tid == tenant_id
            and m.role is MembershipRole.OWNER
            and m.status is MembershipStatus.ACTIVE
        )

    def update_checked(self, membership: Membership, *, expected_version: int) -> None:
        key = (membership.tenant_id.value, membership.user_id.value)
        current = self.store.get(key)
        if current is None or current.version != expected_version:
            raise MembershipConcurrencyError("stale")
        bumped = replace(membership, version=expected_version + 1)
        self.store[key] = bumped
        self.updated.append(bumped)


class FakeApprovalResponsibilityQuery:
    def __init__(self, with_responsibility: set[UUID] | None = None) -> None:
        self._users = with_responsibility or set()

    def has_active_responsibilities(self, *, tenant_id: UUID, user_id: UUID) -> bool:
        return user_id in self._users


class FakeMemberUpdateUnitOfWork:
    def __init__(
        self,
        memberships: FakeMembershipManagementRepository,
        approval_responsibility: FakeApprovalResponsibilityQuery,
        audit: object,
    ) -> None:
        self.memberships = memberships
        self.approval_responsibility = approval_responsibility
        self.audit = audit
        self.committed = 0
        self.rolled_back = 0
        self.tenant_context: UUID | None = None
        self.actor_context: UUID | None = None

    def __enter__(self) -> FakeMemberUpdateUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rolled_back += 1

    def set_actor_context(self, actor_user_id: UUID) -> None:
        self.actor_context = actor_user_id

    def set_tenant_context(self, tenant_id: UUID) -> None:
        self.tenant_context = tenant_id

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1


class FakeMemberAuditWriter:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        self.records.append(record)
