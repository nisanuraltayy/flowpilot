"""Üye yönetimi — GERÇEK PostgreSQL RLS + eşzamanlılık (Testcontainers).

RLS: cross-tenant izolasyon, default-deny, UPDATE policy, DELETE imkânsız, soft-remove
kalıcılığı, optimistic CAS, email join sızıntısı yok.
Concurrency: iki stale update'ten biri kazanır; iki owner birbirini düşüremez (en az bir
aktif owner kalır); başarılı güncelleme başına tek audit seti.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.organization.application.member_dto import UpdateMemberCommand
from flowpilot.modules.organization.application.member_errors import (
    FinalOwnerError,
    MemberManagementForbiddenError,
    MemberNotFoundError,
    MembershipConcurrencyError,
)
from tests.integration.invitation_support import (
    add_member,
    audit_event_count,
    build_update_member_handler,
    create_tenant_with_owner,
    membership_row,
)

pytestmark = pytest.mark.integration


def _active_owner_count(app_sessionmaker: sessionmaker[Session], *, tenant_id: UUID) -> int:
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        value = s.execute(
            text(
                "SELECT count(*) FROM organization_memberships "
                "WHERE tenant_id = :t AND role = 'owner' AND status = 'active'"
            ),
            {"t": str(tenant_id)},
        ).scalar_one()
    return int(value)


# =============================== RLS ========================================


def test_cross_tenant_update_target_invisible(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_a, _owner_a = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-a")
    member_a = add_member(app_sessionmaker, tenant_id=tenant_a, subject="member-a", role="member")
    tenant_b, owner_b = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-b")

    handler = build_update_member_handler(app_sessionmaker)
    # Tenant B'nin owner'ı, Tenant A'nın üyesini B scope'unda güncelleyemez → hedef görünmez.
    with pytest.raises(MemberNotFoundError):
        handler.handle(
            UpdateMemberCommand(
                tenant_id=tenant_b,
                actor_user_id=owner_b,
                target_user_id=member_a,
                new_role="admin",
                new_status=None,
                expected_version=1,
            )
        )


def test_delete_denied_for_app_role(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_id, _owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    member_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="m", role="member")
    # No DELETE grant → permission denied (soft-remove; fiziksel silme yok).
    with pytest.raises(ProgrammingError), app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"),
            {"t": str(tenant_id)},
        )
        s.execute(
            text("DELETE FROM organization_memberships WHERE tenant_id = :t AND user_id = :u"),
            {"t": str(tenant_id), "u": str(member_id)},
        )


def test_removed_row_physically_remains(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    member_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="m", role="member")
    handler = build_update_member_handler(app_sessionmaker)
    handler.handle(
        UpdateMemberCommand(
            tenant_id=tenant_id,
            actor_user_id=owner_id,
            target_user_id=member_id,
            new_role=None,
            new_status="removed",
            expected_version=1,
        )
    )
    row = membership_row(app_sessionmaker, tenant_id=tenant_id, user_id=member_id)
    assert row is not None and row["status"] == "removed"  # satır fiziksel olarak durur


def test_update_bumps_version_and_updated_at(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    member_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="m", role="member")

    def _snapshot() -> tuple[int, object]:
        with app_sessionmaker() as s, s.begin():
            s.execute(
                text("SELECT set_config('app.current_tenant_id', :t, true)"),
                {"t": str(tenant_id)},
            )
            r = s.execute(
                text(
                    "SELECT version, updated_at FROM organization_memberships "
                    "WHERE tenant_id = :t AND user_id = :u"
                ),
                {"t": str(tenant_id), "u": str(member_id)},
            ).one()
        return int(r[0]), r[1]

    before_version, before_updated = _snapshot()
    handler = build_update_member_handler(app_sessionmaker)
    handler.handle(
        UpdateMemberCommand(
            tenant_id=tenant_id,
            actor_user_id=owner_id,
            target_user_id=member_id,
            new_role="admin",
            new_status=None,
            expected_version=before_version,
        )
    )
    after_version, after_updated = _snapshot()
    assert after_version == before_version + 1
    assert after_updated >= before_updated


def test_list_does_not_leak_other_tenant_emails(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    from tests.integration.invitation_support import build_list_members_handler

    tenant_a, owner_a = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-a")
    add_member(app_sessionmaker, tenant_id=tenant_a, subject="member-a", role="member")
    tenant_b, _ = create_tenant_with_owner(app_sessionmaker, owner_subject="owner-b")
    add_member(app_sessionmaker, tenant_id=tenant_b, subject="member-b", role="member")

    handler = build_list_members_handler(app_sessionmaker)
    views = handler.handle(tenant_id=tenant_a, actor_user_id=owner_a, limit=50)
    emails = {v.email for v in views}
    assert "member-a@example.com" in emails
    assert "member-b@example.com" not in emails  # başka tenant'ın email'i sızmaz
    assert "owner-b@example.com" not in emails


# =============================== Concurrency ================================


def _run_concurrently(
    fns: list[Callable[[], object]],
) -> list[tuple[object, Exception | None]]:
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


def test_two_stale_updates_one_wins(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="owner")
    member_id = add_member(app_sessionmaker, tenant_id=tenant_id, subject="m", role="member")
    handler = build_update_member_handler(app_sessionmaker)

    def _promote() -> object:
        return handler.handle(
            UpdateMemberCommand(
                tenant_id=tenant_id,
                actor_user_id=owner_id,
                target_user_id=member_id,
                new_role="admin",
                new_status=None,
                expected_version=1,
            )
        )

    results = _run_concurrently([_promote, _promote])
    successes = [r for r, e in results if e is None]
    errors = [e for _, e in results if e is not None]
    assert len(successes) == 1, results
    assert len(errors) == 1 and isinstance(errors[0], MembershipConcurrencyError)

    row = membership_row(app_sessionmaker, tenant_id=tenant_id, user_id=member_id)
    assert row is not None and row["role"] == "admin"
    # Tek başarılı güncelleme → tek role_changed audit.
    assert (
        audit_event_count(
            app_sessionmaker,
            tenant_id=tenant_id,
            event_type="organization.membership.role_changed",
        )
        == 1
    )


def test_two_owners_demote_each_other_one_remains(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_id, owner1 = create_tenant_with_owner(app_sessionmaker, owner_subject="owner1")
    owner2 = add_member(app_sessionmaker, tenant_id=tenant_id, subject="owner2", role="owner")
    handler = build_update_member_handler(app_sessionmaker)

    def _demote(actor: UUID, target: UUID) -> object:
        return handler.handle(
            UpdateMemberCommand(
                tenant_id=tenant_id,
                actor_user_id=actor,
                target_user_id=target,
                new_role="admin",
                new_status=None,
                expected_version=1,
            )
        )

    results = _run_concurrently([lambda: _demote(owner1, owner2), lambda: _demote(owner2, owner1)])
    successes = [r for r, e in results if e is None]
    errors = [e for _, e in results if e is not None]
    # Advisory lock serileştirir: tam biri başarılı, biri reddedilir (invariant korunur).
    assert len(successes) == 1, results
    assert len(errors) == 1
    assert isinstance(errors[0], (FinalOwnerError, MemberManagementForbiddenError)), errors[0]
    # En az bir aktif owner kalır (tam olarak bir).
    assert _active_owner_count(app_sessionmaker, tenant_id=tenant_id) == 1
