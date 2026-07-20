"""Approval rol atama ↔ workflow task pinning — GERÇEK PostgreSQL (snapshot davranışı).

Yeni task oluşturulduğu anki assignee'ye pinlenir; sonraki reassignment MEVCUT task'ı
DEĞİŞTİRMEZ; yalnız sonraki satın alma talepleri yeni assignee'yi kullanır. Inbox yalnız
pinlenmiş kullanıcıya görev gösterir.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.api.wiring import SqlAlchemyTaskInboxReadModel
from flowpilot.modules.approval.application.role_assignment_dto import AssignApprovalRoleCommand
from flowpilot.modules.purchase_request.application.dto import CreatePurchaseRequestCommand
from tests.integration.approval_role_support import (
    build_assign_approval_role_handler,
    task_assignee,
)
from tests.integration.invitation_support import add_member, create_tenant_with_owner
from tests.integration.purchase_support import (
    AMOUNT_OVER_50K,
    AMOUNT_UNDER_10K,
    build_create_handler,
)

pytestmark = pytest.mark.integration


def _assign(
    tenant: UUID, actor: UUID, role: str, target: UUID, ev: int | None
) -> AssignApprovalRoleCommand:
    return AssignApprovalRoleCommand(
        tenant_id=tenant,
        actor_user_id=actor,
        role_key=role,
        target_user_id=target,
        expected_version=ev,
    )


def _pr(tenant: UUID, actor: UUID, amount: int) -> CreatePurchaseRequestCommand:
    return CreatePurchaseRequestCommand(
        actor_user_id=actor,
        tenant_id=tenant,
        title="Ekipman",
        description="ekip için",
        amount_minor=amount,
        currency="TRY",
    )


def _inbox_task_ids(
    app_sessionmaker: sessionmaker[Session], *, tenant: UUID, user: UUID
) -> set[UUID]:
    items = SqlAlchemyTaskInboxReadModel(app_sessionmaker).list_pending_for_user(
        tenant_id=tenant, user_id=user, limit=50
    )
    return {item.task_id for item in items}


def test_active_task_pins_to_current_assignee_and_survives_reassignment(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant, owner = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    user_a = add_member(app_sessionmaker, tenant_id=tenant, subject="a", role="member")
    user_b = add_member(app_sessionmaker, tenant_id=tenant, subject="b", role="member")
    assign = build_assign_approval_role_handler(app_sessionmaker)
    create = build_create_handler(app_sessionmaker)

    # 1) team_manager → A. 2) PR oluştur → ilk task A'ya pinlenir.
    assign.handle(_assign(tenant, owner, "team_manager", user_a, None))
    pr1 = create.handle(_pr(tenant, owner, AMOUNT_UNDER_10K))
    task1_role = "team_manager"
    assert (
        task_assignee(
            app_sessionmaker,
            tenant_id=tenant,
            instance_id=pr1.workflow_instance_id,
            role=task1_role,
        )
        == user_a
    )

    # 3) Inbox: A görür, B görmez.
    inbox_a = _inbox_task_ids(app_sessionmaker, tenant=tenant, user=user_a)
    assert len(inbox_a) == 1
    assert _inbox_task_ids(app_sessionmaker, tenant=tenant, user=user_b) == set()

    # 4) team_manager → B (reassignment). 5) Eski task DEĞİŞMEZ (hâlâ A).
    assign.handle(_assign(tenant, owner, "team_manager", user_b, 1))
    assert (
        task_assignee(
            app_sessionmaker,
            tenant_id=tenant,
            instance_id=pr1.workflow_instance_id,
            role=task1_role,
        )
        == user_a
    )
    # Eski task hâlâ A'nın inbox'unda; B'de değil.
    assert _inbox_task_ids(app_sessionmaker, tenant=tenant, user=user_a) == inbox_a
    assert _inbox_task_ids(app_sessionmaker, tenant=tenant, user=user_b) == set()

    # 6) Sonraki PR yeni assignee'yi (B) kullanır.
    pr2 = create.handle(_pr(tenant, owner, AMOUNT_UNDER_10K))
    assert (
        task_assignee(
            app_sessionmaker,
            tenant_id=tenant,
            instance_id=pr2.workflow_instance_id,
            role=task1_role,
        )
        == user_b
    )
    inbox_b = _inbox_task_ids(app_sessionmaker, tenant=tenant, user=user_b)
    assert len(inbox_b) == 1
    # A'nın inbox'u değişmedi (yalnız eski task).
    assert _inbox_task_ids(app_sessionmaker, tenant=tenant, user=user_a) == inbox_a


def test_finance_step_pins_per_creation_time_assignment(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant, owner = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    user_a = add_member(app_sessionmaker, tenant_id=tenant, subject="fa", role="member")
    user_b = add_member(app_sessionmaker, tenant_id=tenant, subject="fb", role="member")
    assign = build_assign_approval_role_handler(app_sessionmaker)
    create = build_create_handler(app_sessionmaker)

    # finance → A; >50k PR → finance step (pending) A'ya pinlenir.
    assign.handle(_assign(tenant, owner, "finance", user_a, None))
    pr1 = create.handle(_pr(tenant, owner, AMOUNT_OVER_50K))
    assert (
        task_assignee(
            app_sessionmaker, tenant_id=tenant, instance_id=pr1.workflow_instance_id, role="finance"
        )
        == user_a
    )

    # finance → B; sonraki >50k PR'ın finance step'i B; eski PR'ınki hâlâ A.
    assign.handle(_assign(tenant, owner, "finance", user_b, 1))
    pr2 = create.handle(_pr(tenant, owner, AMOUNT_OVER_50K))
    assert (
        task_assignee(
            app_sessionmaker, tenant_id=tenant, instance_id=pr2.workflow_instance_id, role="finance"
        )
        == user_b
    )
    assert (
        task_assignee(
            app_sessionmaker, tenant_id=tenant, instance_id=pr1.workflow_instance_id, role="finance"
        )
        == user_a
    )  # geçmiş task yeniden yazılmaz
