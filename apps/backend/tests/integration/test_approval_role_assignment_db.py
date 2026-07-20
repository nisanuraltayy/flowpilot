"""Approval rol atama — GERÇEK PostgreSQL RLS + eşzamanlılık (Testcontainers).

RLS: cross-tenant izolasyon, DELETE imkânsız, tek aktif atama, revoked geçmişi, email
sızıntısı yok. Concurrency: iki eşzamanlı farklı-user atamada yalnız biri kazanır (tek aktif
atama + tek audit); stale expected_version state değiştirmez.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.approval.application.role_assignment_dto import AssignApprovalRoleCommand
from flowpilot.modules.approval.application.role_assignment_errors import (
    ApprovalRoleActorNotMemberError,
    ApprovalRoleAssignmentConcurrencyError,
)
from tests.integration.approval_role_support import (
    active_assignment,
    assignment_rows,
    build_assign_approval_role_handler,
    build_list_approval_roles_handler,
)
from tests.integration.invitation_support import (
    add_member,
    audit_event_count,
    create_tenant_with_owner,
)

pytestmark = pytest.mark.integration

_CHANGED = "approval.role_assignment.changed"


def _cmd(tenant: UUID, actor: UUID, target: UUID, *, ev: int | None) -> AssignApprovalRoleCommand:
    return AssignApprovalRoleCommand(
        tenant_id=tenant,
        actor_user_id=actor,
        role_key="finance",
        target_user_id=target,
        expected_version=ev,
    )


# =============================== RLS ========================================


def test_reassign_keeps_single_active_and_revoked_history(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant, owner = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    a = add_member(app_sessionmaker, tenant_id=tenant, subject="a", role="member")
    b = add_member(app_sessionmaker, tenant_id=tenant, subject="b", role="member")
    handler = build_assign_approval_role_handler(app_sessionmaker)

    handler.handle(_cmd(tenant, owner, a, ev=None))  # create v1 → A
    handler.handle(_cmd(tenant, owner, b, ev=1))  # reassign → B v2

    rows = assignment_rows(app_sessionmaker, tenant_id=tenant)
    finance = [r for r in rows if r["role_key"] == "finance"]
    active = [r for r in finance if r["status"] == "active"]
    revoked = [r for r in finance if r["status"] == "revoked"]
    assert len(active) == 1 and active[0]["assigned_user_id"] == b and active[0]["version"] == 2
    assert len(revoked) == 1 and revoked[0]["assigned_user_id"] == a  # geçmiş korunur


def test_delete_denied_for_app_role(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant, owner = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    a = add_member(app_sessionmaker, tenant_id=tenant, subject="a", role="member")
    build_assign_approval_role_handler(app_sessionmaker).handle(_cmd(tenant, owner, a, ev=None))
    with pytest.raises(ProgrammingError), app_sessionmaker() as s, s.begin():
        s.execute(text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant)})
        s.execute(
            text("DELETE FROM approval_role_assignments WHERE tenant_id = :t"), {"t": str(tenant)}
        )


def test_cross_tenant_actor_not_member(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_a, owner_a = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-a")
    a = add_member(app_sessionmaker, tenant_id=tenant_a, subject="a", role="member")
    tenant_b, _owner_b = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-b")
    handler = build_assign_approval_role_handler(app_sessionmaker)
    # owner A, tenant B'de üye değil → 404.
    with pytest.raises(ApprovalRoleActorNotMemberError):
        handler.handle(_cmd(tenant_b, owner_a, a, ev=None))


def test_list_does_not_leak_other_tenant(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_a, owner_a = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-a")
    a = add_member(app_sessionmaker, tenant_id=tenant_a, subject="fin-a", role="member")
    tenant_b, owner_b = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-b")
    b = add_member(app_sessionmaker, tenant_id=tenant_b, subject="fin-b", role="member")
    assign = build_assign_approval_role_handler(app_sessionmaker)
    assign.handle(_cmd(tenant_a, owner_a, a, ev=None))
    assign.handle(_cmd(tenant_b, owner_b, b, ev=None))

    listing = build_list_approval_roles_handler(app_sessionmaker)
    views_a = listing.handle(tenant_id=tenant_a, actor_user_id=owner_a)
    emails_a = {v.assigned_user_email for v in views_a}
    assert "fin-a@example.com" in emails_a
    assert "fin-b@example.com" not in emails_a  # başka tenant sızmaz
    users_a = {v.assigned_user_id for v in views_a}
    assert b not in users_a


# =============================== Concurrency ================================


def _run_concurrently(fns: list[Callable[[], object]]) -> list[tuple[object, Exception | None]]:
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


def test_two_concurrent_reassigns_one_wins(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant, owner = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    seed = add_member(app_sessionmaker, tenant_id=tenant, subject="seed", role="member")
    x = add_member(app_sessionmaker, tenant_id=tenant, subject="x", role="member")
    y = add_member(app_sessionmaker, tenant_id=tenant, subject="y", role="member")
    handler = build_assign_approval_role_handler(app_sessionmaker)
    handler.handle(_cmd(tenant, owner, seed, ev=None))  # aktif v1 → seed

    results = _run_concurrently(
        [
            lambda: handler.handle(_cmd(tenant, owner, x, ev=1)),
            lambda: handler.handle(_cmd(tenant, owner, y, ev=1)),
        ]
    )
    successes = [r for r, e in results if e is None]
    errors = [e for _, e in results if e is not None]
    assert len(successes) == 1, results
    assert len(errors) == 1 and isinstance(errors[0], ApprovalRoleAssignmentConcurrencyError)

    active = active_assignment(app_sessionmaker, tenant_id=tenant, role_key="finance")
    assert active is not None and active["assigned_user_id"] in (x, y) and active["version"] == 2
    # seed(1) + tek kazanan(1) = 2 changed audit; kaybeden audit üretmez.
    assert audit_event_count(app_sessionmaker, tenant_id=tenant, event_type=_CHANGED) == 2
