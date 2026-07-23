"""Self-approval — GERÇEK PostgreSQL RLS + eşzamanlılık (Testcontainers).

RLS: cross-tenant blocked task görünmez/çözülemez, DELETE reddi, blocked_reason CHECK.
Concurrency: iki eşzamanlı resolve → tek kazanan; requester karar ile resolve yarışında
requester ASLA kazanamaz.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
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
from tests.integration.invitation_support import add_member, create_tenant_with_owner
from tests.integration.purchase_support import (
    AMOUNT_UNDER_10K,
    build_create_handler,
    build_decide_handler,
)

pytestmark = pytest.mark.integration


def _assign(app_sm: sessionmaker[Session], tenant: UUID, owner: UUID, role: str, tgt: UUID) -> None:
    current = active_assignment(app_sm, tenant_id=tenant, role_key=role)
    build_assign_approval_role_handler(app_sm).handle(
        AssignApprovalRoleCommand(
            tenant_id=tenant,
            actor_user_id=owner,
            role_key=role,
            target_user_id=tgt,
            expected_version=int(current["version"]) if current else None,
        )
    )


def _blocked_pr(app_sm: sessionmaker[Session]) -> tuple[UUID, UUID, UUID, UUID]:
    """(tenant, requester, approver, blocked_task_id) — team_manager=requester → step0 blocked."""
    tenant, requester = create_tenant_with_owner(app_sm, owner_subject="req")
    approver = add_member(app_sm, tenant_id=tenant, subject="appr", role="member")
    _assign(app_sm, tenant, requester, "team_manager", requester)
    created = build_create_handler(app_sm).handle(
        CreatePurchaseRequestCommand(
            actor_user_id=requester,
            tenant_id=tenant,
            title="T",
            description=None,
            amount_minor=AMOUNT_UNDER_10K,
            currency="TRY",
        )
    )
    row = task_row(
        app_sm, tenant_id=tenant, instance_id=created.workflow_instance_id, role="team_manager"
    )
    return tenant, requester, approver, UUID(str(row["id"]))  # type: ignore[index]


# =============================== RLS ========================================


def test_cross_tenant_blocked_not_listed(app_sessionmaker: sessionmaker[Session]) -> None:
    _tenant_a, _req, _appr, _task = _blocked_pr(app_sessionmaker)
    tenant_b, owner_b = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-b")
    # Tenant B owner'ı yalnız B scope'unu görür → A'nın blocked task'ı görünmez.
    blocked_b = build_list_blocked_tasks_handler(app_sessionmaker).handle(
        tenant_id=tenant_b, actor_user_id=owner_b, limit=50
    )
    assert blocked_b == []


def test_delete_denied_for_app_role(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant, _req, _appr, task_id = _blocked_pr(app_sessionmaker)
    with pytest.raises(ProgrammingError), app_sessionmaker() as s, s.begin():
        s.execute(text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant)})
        s.execute(text("DELETE FROM workflow_runtime_tasks WHERE id = :i"), {"i": str(task_id)})


def test_invalid_blocked_reason_rejected(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant, _req, _appr, task_id = _blocked_pr(app_sessionmaker)
    with pytest.raises(IntegrityError), app_sessionmaker() as s, s.begin():
        s.execute(text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant)})
        s.execute(
            text("UPDATE workflow_runtime_tasks SET blocked_reason = 'bogus' WHERE id = :i"),
            {"i": str(task_id)},
        )


# =============================== Concurrency ================================


def _run(fns: list[Callable[[], object]]) -> list[tuple[object, Exception | None]]:
    barrier = threading.Barrier(len(fns))
    results: list[tuple[object, Exception | None]] = [(None, None)] * len(fns)

    def _wrap(index: int, fn: Callable[[], object]) -> None:
        barrier.wait()
        try:
            results[index] = (fn(), None)
        except Exception as exc:  # her iki thread'in sonucunu topla
            results[index] = (None, exc)

    threads = [threading.Thread(target=_wrap, args=(i, fn)) for i, fn in enumerate(fns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def test_two_concurrent_resolves_one_wins(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant, requester, approver, task_id = _blocked_pr(app_sessionmaker)
    _assign(app_sessionmaker, tenant, requester, "team_manager", approver)  # uygun aday
    handler = build_resolve_blocked_task_handler(app_sessionmaker)

    def _resolve() -> object:
        return handler.handle(
            ResolveBlockedTaskCommand(tenant_id=tenant, actor_user_id=requester, task_id=task_id)
        )

    results = _run([_resolve, _resolve])
    successes = [r for r, e in results if e is None]
    errors = [e for _, e in results if e is not None]
    assert len(successes) == 1, results
    assert len(errors) == 1 and isinstance(errors[0], BlockedTaskResolveConflictError)
    # Task tam olarak bir kez active + approver'a atalı.
    row = task_row(
        app_sessionmaker,
        tenant_id=tenant,
        instance_id=_instance_of(app_sessionmaker, tenant, task_id),
        role="team_manager",
    )
    assert row is not None and row["status"] == "active"
    assert UUID(str(row["assigned_user_id"])) == approver


def test_requester_decision_never_wins_against_resolve(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant, requester, approver, task_id = _blocked_pr(app_sessionmaker)
    _assign(app_sessionmaker, tenant, requester, "team_manager", approver)
    resolver = build_resolve_blocked_task_handler(app_sessionmaker)
    decider = build_decide_handler(app_sessionmaker)

    def _resolve() -> object:
        return resolver.handle(
            ResolveBlockedTaskCommand(tenant_id=tenant, actor_user_id=requester, task_id=task_id)
        )

    def _requester_decide() -> object:
        return decider.handle(
            DecideApprovalTaskCommand(
                tenant_id=tenant,
                actor_user_id=requester,
                task_id=task_id,
                decision="approve",
                comment=None,
                idempotency_key="self-race",
            )
        )

    results = _run([_resolve, _requester_decide])
    # requester kararı DAİMA reddedilir (SelfApprovalConflict) — asla approved olmaz.
    decide_outcome = results[1]
    assert decide_outcome[0] is None
    assert isinstance(
        decide_outcome[1], (SelfApprovalConflictError, BlockedTaskResolveConflictError)
    )
    # DB'de requester adına karar kaydı YOK.
    from tests.integration.purchase_support import scoped_count

    assert scoped_count(app_sessionmaker, tenant, "approval_decisions", task_id=str(task_id)) == 0


def _instance_of(app_sm: sessionmaker[Session], tenant: UUID, task_id: UUID) -> UUID:
    with app_sm() as s, s.begin():
        s.execute(text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant)})
        row = s.execute(
            text("SELECT instance_id FROM workflow_runtime_tasks WHERE id = :i"),
            {"i": str(task_id)},
        ).one()
    return UUID(str(row[0]))
