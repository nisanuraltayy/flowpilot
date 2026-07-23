"""Self-approval engelleme — workflow sequential davranışı (GERÇEK PostgreSQL).

Talep sahibi kendi talebindeki adımın çözülen assignee'si olduğunda o adım blocked olur
(talep sahibine atanmaz, inbox'ta görünmez); rol düzeltilip resolve edilince akış devam eder.
Karar anı savunması: talep sahibi doğrudan karar veremez (409). Normal task pinning bozulmaz.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.approval.application.blocked_task_dto import ResolveBlockedTaskCommand
from flowpilot.modules.approval.application.blocked_task_errors import (
    BlockedTaskResolveConflictError,
)
from flowpilot.modules.approval.application.dto import DecideApprovalTaskCommand
from flowpilot.modules.approval.application.errors import SelfApprovalConflictError
from flowpilot.modules.approval.application.role_assignment_dto import AssignApprovalRoleCommand
from flowpilot.modules.purchase_request.application.dto import CreatePurchaseRequestCommand
from tests.integration.approval_role_support import (
    active_assignment,
    build_assign_approval_role_handler,
)
from tests.integration.blocked_task_support import (
    build_list_blocked_tasks_handler,
    build_resolve_blocked_task_handler,
    task_row,
)
from tests.integration.invitation_support import (
    add_member,
    audit_event_count,
    create_tenant_with_owner,
)
from tests.integration.purchase_support import (
    AMOUNT_10K,
    AMOUNT_OVER_50K,
    AMOUNT_UNDER_10K,
    active_task_id,
    build_create_handler,
    build_decide_handler,
)

pytestmark = pytest.mark.integration

_ROLES = ("team_manager", "finance", "general_manager")


def _assign(
    app_sessionmaker: sessionmaker[Session], tenant: UUID, owner: UUID, role: str, target: UUID
) -> None:
    current = active_assignment(app_sessionmaker, tenant_id=tenant, role_key=role)
    build_assign_approval_role_handler(app_sessionmaker).handle(
        AssignApprovalRoleCommand(
            tenant_id=tenant,
            actor_user_id=owner,
            role_key=role,
            target_user_id=target,
            expected_version=int(current["version"]) if current else None,
        )
    )


def _create_pr(app_sessionmaker: sessionmaker[Session], tenant: UUID, actor: UUID, amount: int):
    return build_create_handler(app_sessionmaker).handle(
        CreatePurchaseRequestCommand(
            actor_user_id=actor,
            tenant_id=tenant,
            title="Talep",
            description=None,
            amount_minor=amount,
            currency="TRY",
        )
    )


def test_requester_is_manager_first_step_blocked(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant, requester = create_tenant_with_owner(app_sessionmaker, owner_subject="req")
    # team_manager = requester → 12.500 TL PR'ın ilk adımı blocked (talep sahibine atanmaz).
    _assign(app_sessionmaker, tenant, requester, "team_manager", requester)
    approver = add_member(app_sessionmaker, tenant_id=tenant, subject="fin", role="member")
    _assign(app_sessionmaker, tenant, requester, "finance", approver)

    created = _create_pr(app_sessionmaker, tenant, requester, AMOUNT_10K)
    tm = task_row(
        app_sessionmaker,
        tenant_id=tenant,
        instance_id=created.workflow_instance_id,
        role="team_manager",
    )
    assert tm is not None and tm["status"] == "blocked"
    assert tm["assigned_user_id"] is None  # talep sahibine ATANMAZ
    assert tm["blocked_reason"] == "self_approval_no_eligible_assignee"

    # blocked-list owner'a görünür; requester inbox'ında yok (no active task).
    blocked = build_list_blocked_tasks_handler(app_sessionmaker).handle(
        tenant_id=tenant, actor_user_id=requester, limit=50
    )
    assert len(blocked) == 1 and blocked[0].approver_role == "team_manager"
    assert blocked[0].requester_user_id == requester


def test_requester_is_finance_blocks_after_manager_approves(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant, requester = create_tenant_with_owner(app_sessionmaker, owner_subject="req")
    manager = add_member(app_sessionmaker, tenant_id=tenant, subject="mgr", role="member")
    _assign(app_sessionmaker, tenant, requester, "team_manager", manager)
    _assign(app_sessionmaker, tenant, requester, "finance", requester)  # requester = finance

    created = _create_pr(app_sessionmaker, tenant, requester, AMOUNT_10K)  # team_manager, finance
    # İlk adım manager'a atanır (aktif); manager onaylar → finance adımı blocked olur.
    task = active_task_id(app_sessionmaker, tenant, created.workflow_instance_id)
    build_decide_handler(app_sessionmaker).handle(
        DecideApprovalTaskCommand(
            tenant_id=tenant,
            actor_user_id=manager,
            task_id=task,
            decision="approve",
            comment=None,
            idempotency_key="k1",
        )
    )
    fin = task_row(
        app_sessionmaker, tenant_id=tenant, instance_id=created.workflow_instance_id, role="finance"
    )
    assert fin is not None and fin["status"] == "blocked" and fin["assigned_user_id"] is None


def test_requester_is_gm_blocks_at_last_step(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant, requester = create_tenant_with_owner(app_sessionmaker, owner_subject="req")
    approver = add_member(app_sessionmaker, tenant_id=tenant, subject="appr", role="member")
    _assign(app_sessionmaker, tenant, requester, "team_manager", approver)
    _assign(app_sessionmaker, tenant, requester, "finance", approver)
    _assign(app_sessionmaker, tenant, requester, "general_manager", requester)  # requester = GM

    created = _create_pr(app_sessionmaker, tenant, requester, AMOUNT_OVER_50K)  # 3 adım
    inst = created.workflow_instance_id
    decider = build_decide_handler(app_sessionmaker)
    for i, role in enumerate(("team_manager", "finance")):
        task = active_task_id(app_sessionmaker, tenant, inst)
        decider.handle(
            DecideApprovalTaskCommand(
                tenant_id=tenant,
                actor_user_id=approver,
                task_id=task,
                decision="approve",
                comment=None,
                idempotency_key=f"k{i}",
            )
        )
        del role
    gm = task_row(app_sessionmaker, tenant_id=tenant, instance_id=inst, role="general_manager")
    assert gm is not None and gm["status"] == "blocked"


def test_resolve_unblocks_and_flow_completes(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant, requester = create_tenant_with_owner(app_sessionmaker, owner_subject="req")
    _assign(app_sessionmaker, tenant, requester, "team_manager", requester)  # blocked at step 0
    created = _create_pr(app_sessionmaker, tenant, requester, AMOUNT_UNDER_10K)  # tek adım
    inst = created.workflow_instance_id
    blocked = task_row(app_sessionmaker, tenant_id=tenant, instance_id=inst, role="team_manager")
    assert blocked is not None and blocked["status"] == "blocked"
    task_id = UUID(str(blocked["id"]))

    # Rol uygun bir kullanıcıya atanır; resolve → task active olur → o kullanıcı onaylar.
    approver = add_member(app_sessionmaker, tenant_id=tenant, subject="appr", role="member")
    _assign(app_sessionmaker, tenant, requester, "team_manager", approver)
    resolved = build_resolve_blocked_task_handler(app_sessionmaker).handle(
        ResolveBlockedTaskCommand(tenant_id=tenant, actor_user_id=requester, task_id=task_id)
    )
    assert resolved.status == "active" and resolved.assigned_user_id == approver

    build_decide_handler(app_sessionmaker).handle(
        DecideApprovalTaskCommand(
            tenant_id=tenant,
            actor_user_id=approver,
            task_id=task_id,
            decision="approve",
            comment=None,
            idempotency_key="k-final",
        )
    )
    after = task_row(app_sessionmaker, tenant_id=tenant, instance_id=inst, role="team_manager")
    assert after is not None and after["status"] == "approved"
    assert (
        audit_event_count(
            app_sessionmaker,
            tenant_id=tenant,
            event_type="approval.task_assignment_resolved",
        )
        == 1
    )


def test_requester_direct_decision_forbidden(app_sessionmaker: sessionmaker[Session]) -> None:
    # Assignee yanlışlıkla requester olsa bile (legacy) karar anı reddedilir.
    tenant, requester = create_tenant_with_owner(app_sessionmaker, owner_subject="req")
    approver = add_member(app_sessionmaker, tenant_id=tenant, subject="appr", role="member")
    _assign(app_sessionmaker, tenant, requester, "team_manager", approver)
    created = _create_pr(app_sessionmaker, tenant, requester, AMOUNT_UNDER_10K)
    task = active_task_id(app_sessionmaker, tenant, created.workflow_instance_id)

    # requester approver DEĞİL; yine de kendi talebini onaylamaya çalışırsa → SelfApprovalConflict.
    with pytest.raises(SelfApprovalConflictError):
        build_decide_handler(app_sessionmaker).handle(
            DecideApprovalTaskCommand(
                tenant_id=tenant,
                actor_user_id=requester,
                task_id=task,
                decision="approve",
                comment=None,
                idempotency_key="self",
            )
        )
    # Güvenlik audit'i yazılır; karar/state değişmez (task hâlâ active).
    assert (
        audit_event_count(
            app_sessionmaker, tenant_id=tenant, event_type="approval.self_approval_blocked"
        )
        == 1
    )
    row = task_row(
        app_sessionmaker,
        tenant_id=tenant,
        instance_id=created.workflow_instance_id,
        role="team_manager",
    )
    assert row is not None and row["status"] == "active"


def test_resolve_requires_eligible_non_requester(app_sessionmaker: sessionmaker[Session]) -> None:
    # team_manager hâlâ requester'a atanmışsa resolve 409 (aday requester olamaz).
    tenant, requester = create_tenant_with_owner(app_sessionmaker, owner_subject="req")
    _assign(app_sessionmaker, tenant, requester, "team_manager", requester)
    created = _create_pr(app_sessionmaker, tenant, requester, AMOUNT_UNDER_10K)
    blocked = task_row(
        app_sessionmaker,
        tenant_id=tenant,
        instance_id=created.workflow_instance_id,
        role="team_manager",
    )
    task_id = UUID(str(blocked["id"]))  # type: ignore[index]
    with pytest.raises(BlockedTaskResolveConflictError):
        build_resolve_blocked_task_handler(app_sessionmaker).handle(
            ResolveBlockedTaskCommand(tenant_id=tenant, actor_user_id=requester, task_id=task_id)
        )
