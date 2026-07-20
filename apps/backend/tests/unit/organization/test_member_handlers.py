"""Üye listeleme + güncelleme use-case birim testleri (fake adapter'larla)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from flowpilot.modules.authorization.application.access import PermissionDeniedError
from flowpilot.modules.organization.application.member_dto import (
    MemberView,
    UpdateMemberCommand,
)
from flowpilot.modules.organization.application.member_errors import (
    ApprovalResponsibilityConflictError,
    FinalOwnerError,
    InvalidMemberUpdateError,
    MemberActorNotMemberError,
    MemberManagementForbiddenError,
    MemberNotFoundError,
    MemberSelfMutationError,
    MembershipConcurrencyError,
    MembershipRemovedError,
)
from flowpilot.modules.organization.application.member_handlers import (
    ListOrganizationMembersHandler,
    UpdateOrganizationMemberHandler,
)
from flowpilot.modules.organization.domain.membership import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from flowpilot.shared.identifiers import MembershipId, TenantId, UserId
from tests.unit.fakes import FakeClock, FakeIdGenerator
from tests.unit.organization.invitation_fakes import FakeMembershipQuery
from tests.unit.organization.member_fakes import (
    FakeApprovalResponsibilityQuery,
    FakeMemberAuditWriter,
    FakeMemberListQuery,
    FakeMembershipManagementRepository,
    FakeMemberUpdateUnitOfWork,
)

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
TENANT = uuid4()
OWNER = uuid4()
ADMIN = uuid4()
MEMBER = uuid4()
STRANGER = uuid4()


def _membership(
    user_id: object,
    *,
    role: MembershipRole,
    status: MembershipStatus = MembershipStatus.ACTIVE,
    version: int = 1,
) -> Membership:
    return Membership(
        id=MembershipId(uuid4()),
        tenant_id=TenantId(TENANT),
        user_id=UserId(user_id),  # type: ignore[arg-type]
        role=role,
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
        version=version,
    )


def _actor_memberships() -> FakeMembershipQuery:
    return FakeMembershipQuery(
        {(TENANT, OWNER): "owner", (TENANT, ADMIN): "admin", (TENANT, MEMBER): "member"}
    )


# =============================== LIST =======================================


def _list_handler(
    *, memberships: FakeMembershipQuery | None = None, views: list[MemberView] | None = None
) -> ListOrganizationMembersHandler:
    return ListOrganizationMembersHandler(
        member_list_query=FakeMemberListQuery(views),
        membership_query=memberships or _actor_memberships(),
    )


@pytest.mark.parametrize("actor", [OWNER, ADMIN])
def test_owner_and_admin_can_list(actor: object) -> None:
    view = MemberView(
        membership_id=uuid4(),
        user_id=MEMBER,
        email="m@example.com",
        role="member",
        status="active",
        version=1,
        created_at=_NOW,
        updated_at=_NOW,
    )
    handler = _list_handler(views=[view])
    items = handler.handle(tenant_id=TENANT, actor_user_id=actor, limit=50)  # type: ignore[arg-type]
    assert items == [view]


def test_member_cannot_list() -> None:
    with pytest.raises(PermissionDeniedError):
        _list_handler().handle(tenant_id=TENANT, actor_user_id=MEMBER, limit=50)


def test_non_member_cannot_list() -> None:
    with pytest.raises(MemberActorNotMemberError):
        _list_handler().handle(tenant_id=TENANT, actor_user_id=STRANGER, limit=50)


# =============================== UPDATE =====================================


def _update_handler(
    *,
    targets: dict[tuple, Membership],
    actor_memberships: FakeMembershipQuery | None = None,
    responsibilities: set | None = None,
) -> tuple[UpdateOrganizationMemberHandler, FakeMemberUpdateUnitOfWork]:
    repo = FakeMembershipManagementRepository(targets)
    audit = FakeMemberAuditWriter()
    uow = FakeMemberUpdateUnitOfWork(repo, FakeApprovalResponsibilityQuery(responsibilities), audit)
    handler = UpdateOrganizationMemberHandler(
        unit_of_work_factory=lambda: uow,
        membership_query=actor_memberships or _actor_memberships(),
        clock=FakeClock(_NOW),
        id_generator=FakeIdGenerator([uuid4() for _ in range(10)]),
    )
    return handler, uow


def _cmd(
    *,
    actor: object,
    target: object,
    role: str | None = None,
    status: str | None = None,
    version: int = 1,
) -> UpdateMemberCommand:
    return UpdateMemberCommand(
        tenant_id=TENANT,
        actor_user_id=actor,  # type: ignore[arg-type]
        target_user_id=target,  # type: ignore[arg-type]
        new_role=role,
        new_status=status,
        expected_version=version,
    )


def test_owner_promotes_member_to_admin() -> None:
    handler, uow = _update_handler(
        targets={(TENANT, MEMBER): _membership(MEMBER, role=MembershipRole.MEMBER)}
    )
    result = handler.handle(_cmd(actor=OWNER, target=MEMBER, role="admin"))
    assert result.duplicate is False and result.role == "admin" and result.version == 2
    assert uow.committed == 1
    events = [r.event_type.value for r in uow.audit.records]
    assert events == ["organization.membership.role_changed"]


def test_owner_promotes_member_to_owner() -> None:
    handler, _ = _update_handler(
        targets={(TENANT, MEMBER): _membership(MEMBER, role=MembershipRole.MEMBER)}
    )
    result = handler.handle(_cmd(actor=OWNER, target=MEMBER, role="owner"))
    assert result.role == "owner"


def test_owner_demotes_other_owner_when_more_than_one() -> None:
    targets = {
        (TENANT, OWNER): _membership(OWNER, role=MembershipRole.OWNER),
        (TENANT, ADMIN): _membership(ADMIN, role=MembershipRole.OWNER),  # second owner
    }
    handler, _ = _update_handler(targets=targets)
    result = handler.handle(_cmd(actor=OWNER, target=ADMIN, role="admin"))
    assert result.role == "admin"


def test_final_owner_demotion_conflicts() -> None:
    targets = {(TENANT, ADMIN): _membership(ADMIN, role=MembershipRole.OWNER)}  # sole owner
    handler, uow = _update_handler(targets=targets)
    with pytest.raises(FinalOwnerError):
        handler.handle(_cmd(actor=OWNER, target=ADMIN, role="member"))
    assert uow.committed == 0


@pytest.mark.parametrize("new_status", ["suspended", "removed"])
def test_final_owner_deactivation_conflicts(new_status: str) -> None:
    targets = {(TENANT, ADMIN): _membership(ADMIN, role=MembershipRole.OWNER)}
    handler, _ = _update_handler(targets=targets)
    with pytest.raises(FinalOwnerError):
        handler.handle(_cmd(actor=OWNER, target=ADMIN, status=new_status))


def test_admin_promotes_member_to_admin() -> None:
    handler, _ = _update_handler(
        targets={(TENANT, MEMBER): _membership(MEMBER, role=MembershipRole.MEMBER)}
    )
    result = handler.handle(_cmd(actor=ADMIN, target=MEMBER, role="admin"))
    assert result.role == "admin"


def test_admin_cannot_manage_owner_or_admin_target() -> None:
    targets = {
        (TENANT, OWNER): _membership(OWNER, role=MembershipRole.OWNER),
        (TENANT, uuid4()): _membership(uuid4(), role=MembershipRole.ADMIN),
    }
    other_admin = next(k[1] for k, v in targets.items() if v.role is MembershipRole.ADMIN)
    handler, _ = _update_handler(targets=targets)
    with pytest.raises(MemberManagementForbiddenError):
        handler.handle(_cmd(actor=ADMIN, target=OWNER, role="member"))
    with pytest.raises(MemberManagementForbiddenError):
        handler.handle(_cmd(actor=ADMIN, target=other_admin, status="suspended"))


def test_admin_cannot_grant_owner() -> None:
    handler, _ = _update_handler(
        targets={(TENANT, MEMBER): _membership(MEMBER, role=MembershipRole.MEMBER)}
    )
    with pytest.raises(MemberManagementForbiddenError):
        handler.handle(_cmd(actor=ADMIN, target=MEMBER, role="owner"))


def test_member_actor_forbidden() -> None:
    handler, _ = _update_handler(
        targets={(TENANT, ADMIN): _membership(ADMIN, role=MembershipRole.MEMBER)}
    )
    with pytest.raises(PermissionDeniedError):
        handler.handle(_cmd(actor=MEMBER, target=ADMIN, role="admin"))


def test_non_member_actor_not_found() -> None:
    handler, _ = _update_handler(
        targets={(TENANT, MEMBER): _membership(MEMBER, role=MembershipRole.MEMBER)}
    )
    with pytest.raises(MemberActorNotMemberError):
        handler.handle(_cmd(actor=STRANGER, target=MEMBER, role="admin"))


def test_self_mutation_conflicts() -> None:
    handler, _ = _update_handler(
        targets={(TENANT, OWNER): _membership(OWNER, role=MembershipRole.OWNER)}
    )
    with pytest.raises(MemberSelfMutationError):
        handler.handle(_cmd(actor=OWNER, target=OWNER, role="admin"))


def test_target_not_found() -> None:
    handler, _ = _update_handler(targets={})
    with pytest.raises(MemberNotFoundError):
        handler.handle(_cmd(actor=OWNER, target=uuid4(), role="admin"))


@pytest.mark.parametrize(
    ("start", "new_status", "event"),
    [
        ("active", "suspended", "organization.membership.suspended"),
        ("suspended", "active", "organization.membership.reactivated"),
        ("active", "removed", "organization.membership.removed"),
    ],
)
def test_status_transitions_emit_events(start: str, new_status: str, event: str) -> None:
    target = _membership(MEMBER, role=MembershipRole.MEMBER, status=MembershipStatus(start))
    handler, uow = _update_handler(targets={(TENANT, MEMBER): target})
    result = handler.handle(_cmd(actor=OWNER, target=MEMBER, status=new_status))
    assert result.status == new_status
    assert [r.event_type.value for r in uow.audit.records] == [event]


def test_removed_target_conflicts() -> None:
    target = _membership(MEMBER, role=MembershipRole.MEMBER, status=MembershipStatus.REMOVED)
    handler, _ = _update_handler(targets={(TENANT, MEMBER): target})
    with pytest.raises(MembershipRemovedError):
        handler.handle(_cmd(actor=OWNER, target=MEMBER, role="admin"))


def test_approval_responsibility_blocks_suspend() -> None:
    handler, uow = _update_handler(
        targets={(TENANT, MEMBER): _membership(MEMBER, role=MembershipRole.MEMBER)},
        responsibilities={MEMBER},
    )
    with pytest.raises(ApprovalResponsibilityConflictError):
        handler.handle(_cmd(actor=OWNER, target=MEMBER, status="suspended"))
    assert uow.committed == 0


def test_noop_is_idempotent_duplicate() -> None:
    handler, uow = _update_handler(
        targets={
            (TENANT, MEMBER): _membership(
                MEMBER, role=MembershipRole.MEMBER, status=MembershipStatus.ACTIVE
            )
        }
    )
    result = handler.handle(_cmd(actor=OWNER, target=MEMBER, status="active"))
    assert result.duplicate is True
    assert uow.committed == 0
    assert uow.audit.records == []


def test_stale_version_conflicts() -> None:
    handler, uow = _update_handler(
        targets={(TENANT, MEMBER): _membership(MEMBER, role=MembershipRole.MEMBER, version=5)}
    )
    with pytest.raises(MembershipConcurrencyError):
        handler.handle(_cmd(actor=OWNER, target=MEMBER, role="admin", version=3))
    assert uow.committed == 0


def test_role_and_status_emit_two_events() -> None:
    target = _membership(MEMBER, role=MembershipRole.MEMBER, status=MembershipStatus.ACTIVE)
    handler, uow = _update_handler(targets={(TENANT, MEMBER): target})
    handler.handle(_cmd(actor=OWNER, target=MEMBER, role="admin", status="suspended"))
    events = sorted(r.event_type.value for r in uow.audit.records)
    assert events == ["organization.membership.role_changed", "organization.membership.suspended"]


@pytest.mark.parametrize(
    ("role", "status"),
    [("boss", None), (None, "banished"), (None, None), (None, "invited")],
)
def test_invalid_update_input_422(role: str | None, status: str | None) -> None:
    handler, _ = _update_handler(
        targets={(TENANT, MEMBER): _membership(MEMBER, role=MembershipRole.MEMBER)}
    )
    with pytest.raises(InvalidMemberUpdateError):
        handler.handle(_cmd(actor=OWNER, target=MEMBER, role=role, status=status))
