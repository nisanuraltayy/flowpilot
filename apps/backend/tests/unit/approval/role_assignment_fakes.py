"""Approval rol atama use-case testleri için deterministik fake'ler (pytest toplamaz)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from types import TracebackType
from uuid import UUID

from flowpilot.modules.approval.application.role_assignment_dto import (
    ApprovalRoleAssignmentView,
    TargetMembershipInfo,
)
from flowpilot.modules.approval.application.role_assignment_errors import (
    ApprovalRoleAssignmentConcurrencyError,
)
from flowpilot.modules.approval.domain.enums import ApprovalRoleKey
from flowpilot.modules.approval.domain.models import (
    ApprovalAssignmentStatus,
    ApprovalRoleAssignment,
)
from flowpilot.modules.audit.application.dto import AuditRecord
from flowpilot.modules.organization.application.contracts import ActiveMembershipView


class FakeMembershipQuery:
    """(tenant, user) → rol; yalnız aktif üyelik döner (None = aktif değil)."""

    def __init__(self, active: dict[tuple[UUID, UUID], str] | None = None) -> None:
        self._active = active or {}

    def find_active(self, *, tenant_id: UUID, user_id: UUID) -> ActiveMembershipView | None:
        role = self._active.get((tenant_id, user_id))
        if role is None:
            return None
        return ActiveMembershipView(
            membership_id=user_id, tenant_id=tenant_id, user_id=user_id, role=role
        )

    def find_active_owner(
        self, *, tenant_id: UUID
    ) -> ActiveMembershipView | None:  # pragma: no cover
        return None

    def list_active_for_user(self, *, user_id: UUID) -> list[object]:  # pragma: no cover
        return []


class FakeApprovalRoleListQuery:
    def __init__(self, views: list[ApprovalRoleAssignmentView] | None = None) -> None:
        self.views = views or []

    def list_assignments(self, *, tenant_id: UUID) -> list[ApprovalRoleAssignmentView]:
        return self.views


class FakeTargetMembershipReader:
    def __init__(self, targets: dict[UUID, TargetMembershipInfo] | None = None) -> None:
        self._targets = targets or {}

    def find(self, *, tenant_id: UUID, user_id: UUID) -> TargetMembershipInfo | None:
        return self._targets.get(user_id)


class FakeApprovalRoleManagementRepo:
    """(tenant, role_key) → aktif atama; advisory lock + CAS + revoke/insert taklidi."""

    def __init__(
        self, active: dict[tuple[UUID, str], ApprovalRoleAssignment] | None = None
    ) -> None:
        self.active: dict[tuple[UUID, str], ApprovalRoleAssignment] = dict(active) if active else {}
        self.revoked: list[ApprovalRoleAssignment] = []
        self.inserted: list[ApprovalRoleAssignment] = []
        self.locks: list[tuple[UUID, str]] = []

    def acquire_role_lock(self, *, tenant_id: UUID, role_key: ApprovalRoleKey) -> None:
        self.locks.append((tenant_id, role_key.value))

    def find_active_for_update(
        self, *, tenant_id: UUID, role_key: ApprovalRoleKey
    ) -> ApprovalRoleAssignment | None:
        return self.active.get((tenant_id, role_key.value))

    def revoke_checked(
        self, assignment: ApprovalRoleAssignment, *, expected_version: int, now: datetime
    ) -> None:
        key = (assignment.tenant_id.value, assignment.role_key.value)
        current = self.active.get(key)
        if current is None or current.version != expected_version:
            raise ApprovalRoleAssignmentConcurrencyError("stale")
        self.revoked.append(
            replace(
                current,
                status=ApprovalAssignmentStatus.REVOKED,
                version=expected_version + 1,
                updated_at=now,
            )
        )
        del self.active[key]

    def insert_active(self, assignment: ApprovalRoleAssignment) -> None:
        key = (assignment.tenant_id.value, assignment.role_key.value)
        if key in self.active:
            raise ApprovalRoleAssignmentConcurrencyError("active exists")
        self.active[key] = assignment
        self.inserted.append(assignment)


class FakeAuditWriter:
    def __init__(self, *, fail: bool = False) -> None:
        self.records: list[AuditRecord] = []
        self._fail = fail

    def append(self, record: AuditRecord) -> None:
        if self._fail:
            raise RuntimeError("audit yazımı başarısız")
        self.records.append(record)


class FakeAssignmentUpdateUoW:
    def __init__(
        self,
        assignments: FakeApprovalRoleManagementRepo,
        target_memberships: FakeTargetMembershipReader,
        audit: FakeAuditWriter,
    ) -> None:
        self.assignments = assignments
        self.target_memberships = target_memberships
        self.audit = audit
        self.committed = 0
        self.rolled_back = 0
        self.tenant_context: UUID | None = None
        self.actor_context: UUID | None = None

    def __enter__(self) -> FakeAssignmentUpdateUoW:
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
