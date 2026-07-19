"""EnsureDefaultApprovalRoleAssignments + DefaultApproverResolver birim testleri.

Owner #4: eksik roller aktif owner'a idempotent atanır; owner yoksa kontrollü
configuration error (ActiveOwnerNotFoundError). Public role-management endpoint DEĞİL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from flowpilot.modules.approval.application.ensure_assignments import (
    DefaultApproverResolver,
    EnsureDefaultApprovalRoleAssignments,
)
from flowpilot.modules.approval.application.errors import ActiveOwnerNotFoundError
from flowpilot.modules.approval.domain.models import ApprovalRoleAssignment
from flowpilot.modules.organization.application.contracts import ActiveMembershipView
from flowpilot.shared.identifiers import TenantId
from tests.unit.fakes import FakeClock, FakeIdGenerator

TENANT = uuid4()
OWNER = uuid4()
_NOW = datetime(2026, 7, 19, tzinfo=UTC)


class FakeMembership:
    def __init__(self, owner: UUID | None) -> None:
        self._owner = owner

    def find_active(self, *, tenant_id: UUID, user_id: UUID) -> ActiveMembershipView | None:
        return None

    def find_active_owner(self, *, tenant_id: UUID) -> ActiveMembershipView | None:
        if self._owner is None:
            return None
        return ActiveMembershipView(
            membership_id=uuid4(), tenant_id=tenant_id, user_id=self._owner, role="owner"
        )


class FakeAssignmentRepo:
    def __init__(self) -> None:
        self.added: list[ApprovalRoleAssignment] = []

    def add_if_absent(self, assignment: ApprovalRoleAssignment) -> bool:
        self.added.append(assignment)
        return True


class FakeAssignmentUoW:
    def __init__(self, repo: FakeAssignmentRepo) -> None:
        self.approval_role_assignments = repo
        self.committed = 0

    def __enter__(self) -> FakeAssignmentUoW:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def set_actor_context(self, actor_user_id: UUID) -> None: ...
    def set_tenant_context(self, tenant_id: UUID) -> None: ...

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None: ...


def _ensure(uow: FakeAssignmentUoW, owner: UUID | None) -> EnsureDefaultApprovalRoleAssignments:
    return EnsureDefaultApprovalRoleAssignments(
        unit_of_work_factory=lambda: uow,  # type: ignore[arg-type]
        membership_query=FakeMembership(owner),
        clock=FakeClock(_NOW),
        id_generator=FakeIdGenerator([uuid4() for _ in range(10)]),
    )


def test_all_three_roles_assigned_to_active_owner() -> None:
    repo = FakeAssignmentRepo()
    uow = FakeAssignmentUoW(repo)
    _ensure(uow, OWNER).handle(tenant_id=TenantId(TENANT), actor_user_id=OWNER)

    assert uow.committed == 1
    assert {a.role_key.value for a in repo.added} == {
        "team_manager",
        "finance",
        "general_manager",
    }
    assert all(a.assigned_user_id.value == OWNER for a in repo.added)


def test_no_active_owner_raises_controlled_error() -> None:
    uow = FakeAssignmentUoW(FakeAssignmentRepo())
    with pytest.raises(ActiveOwnerNotFoundError):
        _ensure(uow, owner=None).handle(tenant_id=TenantId(TENANT))
    assert uow.committed == 0


def test_resolver_returns_role_to_user_map() -> None:
    repo = FakeAssignmentRepo()
    uow = FakeAssignmentUoW(repo)
    ensure = _ensure(uow, OWNER)
    mapped = {"team_manager": OWNER, "finance": OWNER, "general_manager": OWNER}

    class FakeQuery:
        def active_map(self, *, tenant_id: UUID) -> dict[str, UUID]:
            return mapped

    resolver = DefaultApproverResolver(ensure=ensure, assignment_query=FakeQuery())
    result = resolver.resolve_all(tenant_id=TENANT, actor_user_id=OWNER)

    assert result == {k: str(v) for k, v in mapped.items()}
    assert uow.committed == 1  # ensure önce çalıştı
