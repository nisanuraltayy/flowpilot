"""Approval rol atama use-case birim testleri (fake'lerle; DB yok)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from flowpilot.modules.approval.application.role_assignment_dto import (
    AssignApprovalRoleCommand,
    TargetMembershipInfo,
)
from flowpilot.modules.approval.application.role_assignment_errors import (
    ApprovalRoleActorNotMemberError,
    ApprovalRoleAssignmentConcurrencyError,
    ApprovalRoleExpectedVersionRequiredError,
    ApprovalRoleTargetNotActiveError,
    ApprovalRoleTargetNotFoundError,
    InvalidApprovalRoleKeyError,
)
from flowpilot.modules.approval.application.role_assignment_handlers import (
    AssignApprovalRoleHandler,
    ListApprovalRoleAssignmentsHandler,
)
from flowpilot.modules.approval.domain.enums import ApprovalRoleKey
from flowpilot.modules.approval.domain.models import (
    ApprovalRoleAssignment,
    ApprovalRoleAssignmentId,
)
from flowpilot.modules.authorization.application.access import PermissionDeniedError
from flowpilot.shared.identifiers import TenantId, UserId
from tests.unit.approval.role_assignment_fakes import (
    FakeApprovalRoleListQuery,
    FakeApprovalRoleManagementRepo,
    FakeAssignmentUpdateUoW,
    FakeAuditWriter,
    FakeMembershipQuery,
    FakeTargetMembershipReader,
)
from tests.unit.fakes import FakeClock, FakeIdGenerator

TENANT = uuid4()
OWNER = uuid4()
ADMIN = uuid4()
MEMBER = uuid4()
TARGET = uuid4()
_NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
_ROLE = "finance"


def _active_assignment(user: UUID, *, version: int = 1) -> ApprovalRoleAssignment:
    return ApprovalRoleAssignment.create_active(
        id=ApprovalRoleAssignmentId(uuid4()),
        tenant_id=TenantId(TENANT),
        role_key=ApprovalRoleKey.FINANCE,
        assigned_user_id=UserId(user),
        created_at=_NOW,
        version=version,
    )


def _memberships(**extra: str) -> FakeMembershipQuery:
    active = {(TENANT, OWNER): "owner", (TENANT, ADMIN): "admin", (TENANT, MEMBER): "member"}
    for user_str, role in extra.items():
        active[(TENANT, UUID(user_str))] = role
    return FakeMembershipQuery(active)


def _build_assign(
    *,
    memberships: FakeMembershipQuery,
    repo: FakeApprovalRoleManagementRepo,
    targets: dict[UUID, TargetMembershipInfo],
    audit: FakeAuditWriter | None = None,
) -> tuple[AssignApprovalRoleHandler, FakeAssignmentUpdateUoW]:
    uow = FakeAssignmentUpdateUoW(
        repo, FakeTargetMembershipReader(targets), audit or FakeAuditWriter()
    )
    handler = AssignApprovalRoleHandler(
        unit_of_work_factory=lambda: uow,
        membership_query=memberships,
        clock=FakeClock(_NOW),
        id_generator=FakeIdGenerator([uuid4() for _ in range(20)]),
    )
    return handler, uow


def _command(
    actor: UUID, target: UUID, *, role: str = _ROLE, ev: int | None = 1
) -> AssignApprovalRoleCommand:
    return AssignApprovalRoleCommand(
        tenant_id=TENANT,
        actor_user_id=actor,
        role_key=role,
        target_user_id=target,
        expected_version=ev,
    )


_ACTIVE_TARGET = {TARGET: TargetMembershipInfo(status="active", email="finance@example.com")}


# ------------------------------- LIST ---------------------------------------


def test_owner_lists() -> None:
    handler = ListApprovalRoleAssignmentsHandler(
        list_query=FakeApprovalRoleListQuery(), membership_query=_memberships()
    )
    assert handler.handle(tenant_id=TENANT, actor_user_id=OWNER) == []


def test_admin_lists() -> None:
    handler = ListApprovalRoleAssignmentsHandler(
        list_query=FakeApprovalRoleListQuery(), membership_query=_memberships()
    )
    assert handler.handle(tenant_id=TENANT, actor_user_id=ADMIN) == []


def test_member_list_forbidden() -> None:
    handler = ListApprovalRoleAssignmentsHandler(
        list_query=FakeApprovalRoleListQuery(), membership_query=_memberships()
    )
    with pytest.raises(PermissionDeniedError):
        handler.handle(tenant_id=TENANT, actor_user_id=MEMBER)


def test_non_member_list_not_found() -> None:
    handler = ListApprovalRoleAssignmentsHandler(
        list_query=FakeApprovalRoleListQuery(), membership_query=_memberships()
    )
    with pytest.raises(ApprovalRoleActorNotMemberError):
        handler.handle(tenant_id=TENANT, actor_user_id=uuid4())


# ------------------------------- ASSIGN -------------------------------------


def test_owner_assigns_to_active_member_creates_when_no_active() -> None:
    repo = FakeApprovalRoleManagementRepo()
    handler, uow = _build_assign(memberships=_memberships(), repo=repo, targets=_ACTIVE_TARGET)
    result = handler.handle(_command(OWNER, TARGET, ev=None))  # no active → create
    assert result.duplicate is False
    assert result.assigned_user_id == TARGET
    assert result.version == 1
    assert result.assigned_user_email == "finance@example.com"
    assert uow.committed == 1
    assert len(repo.inserted) == 1 and len(uow.audit.records) == 1


def test_admin_assigns() -> None:
    repo = FakeApprovalRoleManagementRepo({(TENANT, _ROLE): _active_assignment(OWNER, version=1)})
    handler, uow = _build_assign(memberships=_memberships(), repo=repo, targets=_ACTIVE_TARGET)
    result = handler.handle(_command(ADMIN, TARGET, ev=1))
    assert result.duplicate is False and result.assigned_user_id == TARGET
    # eski revoked, yeni active version 2
    assert result.version == 2
    assert len(repo.revoked) == 1 and repo.revoked[0].assigned_user_id.value == OWNER
    assert uow.audit.records[0].metadata["previous_user_id"] == str(OWNER)


def test_member_actor_forbidden() -> None:
    repo = FakeApprovalRoleManagementRepo()
    handler, _ = _build_assign(memberships=_memberships(), repo=repo, targets=_ACTIVE_TARGET)
    with pytest.raises(PermissionDeniedError):
        handler.handle(_command(MEMBER, TARGET, ev=None))


def test_non_member_actor_not_found() -> None:
    repo = FakeApprovalRoleManagementRepo()
    handler, _ = _build_assign(memberships=_memberships(), repo=repo, targets=_ACTIVE_TARGET)
    with pytest.raises(ApprovalRoleActorNotMemberError):
        handler.handle(_command(uuid4(), TARGET, ev=None))


def test_invalid_role_key_422() -> None:
    repo = FakeApprovalRoleManagementRepo()
    handler, _ = _build_assign(memberships=_memberships(), repo=repo, targets=_ACTIVE_TARGET)
    with pytest.raises(InvalidApprovalRoleKeyError):
        handler.handle(_command(OWNER, TARGET, role="ceo", ev=None))


def test_target_non_member_404() -> None:
    repo = FakeApprovalRoleManagementRepo()
    handler, _ = _build_assign(memberships=_memberships(), repo=repo, targets={})
    with pytest.raises(ApprovalRoleTargetNotFoundError):
        handler.handle(_command(OWNER, TARGET, ev=None))


@pytest.mark.parametrize("status", ["suspended", "removed"])
def test_target_not_active_409(status: str) -> None:
    repo = FakeApprovalRoleManagementRepo()
    handler, _ = _build_assign(
        memberships=_memberships(),
        repo=repo,
        targets={TARGET: TargetMembershipInfo(status=status, email="x@example.com")},
    )
    with pytest.raises(ApprovalRoleTargetNotActiveError):
        handler.handle(_command(OWNER, TARGET, ev=None))


def test_noop_same_user_duplicate() -> None:
    repo = FakeApprovalRoleManagementRepo({(TENANT, _ROLE): _active_assignment(TARGET, version=3)})
    handler, uow = _build_assign(memberships=_memberships(), repo=repo, targets=_ACTIVE_TARGET)
    result = handler.handle(_command(OWNER, TARGET, ev=3))
    assert result.duplicate is True and result.version == 3
    assert uow.committed == 0 and uow.rolled_back == 1
    assert len(repo.inserted) == 0 and len(uow.audit.records) == 0


def test_stale_expected_version_409() -> None:
    repo = FakeApprovalRoleManagementRepo({(TENANT, _ROLE): _active_assignment(OWNER, version=5)})
    handler, uow = _build_assign(memberships=_memberships(), repo=repo, targets=_ACTIVE_TARGET)
    with pytest.raises(ApprovalRoleAssignmentConcurrencyError):
        handler.handle(_command(OWNER, TARGET, ev=1))
    assert uow.committed == 0 and len(uow.audit.records) == 0


def test_expected_version_required_when_active_exists_422() -> None:
    repo = FakeApprovalRoleManagementRepo({(TENANT, _ROLE): _active_assignment(OWNER, version=1)})
    handler, uow = _build_assign(memberships=_memberships(), repo=repo, targets=_ACTIVE_TARGET)
    with pytest.raises(ApprovalRoleExpectedVersionRequiredError):
        handler.handle(_command(OWNER, TARGET, ev=None))
    assert uow.committed == 0


def test_audit_failure_rolls_back() -> None:
    repo = FakeApprovalRoleManagementRepo()
    handler, uow = _build_assign(
        memberships=_memberships(),
        repo=repo,
        targets=_ACTIVE_TARGET,
        audit=FakeAuditWriter(fail=True),
    )
    with pytest.raises(RuntimeError):
        handler.handle(_command(OWNER, TARGET, ev=None))
    assert uow.committed == 0 and uow.rolled_back == 1


def test_reassign_context_set() -> None:
    repo = FakeApprovalRoleManagementRepo()
    handler, uow = _build_assign(memberships=_memberships(), repo=repo, targets=_ACTIVE_TARGET)
    handler.handle(_command(OWNER, TARGET, ev=None))
    assert uow.actor_context == OWNER and uow.tenant_context == TENANT
    assert repo.locks == [(TENANT, _ROLE)]
