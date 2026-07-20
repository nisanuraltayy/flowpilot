"""Üye yönetimi domain birim testleri — geçişler, removed-terminal, invariant policy."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from flowpilot.modules.organization.domain.member_management_policy import (
    MemberManagementForbiddenError,
    authorize_member_change,
)
from flowpilot.modules.organization.domain.membership import (
    InvalidMembershipTransitionError,
    Membership,
    MembershipRemovedError,
    MembershipRole,
    MembershipStatus,
)
from flowpilot.shared.identifiers import MembershipId, TenantId, UserId

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _membership(
    *,
    role: MembershipRole = MembershipRole.MEMBER,
    status: MembershipStatus = MembershipStatus.ACTIVE,
    version: int = 1,
) -> Membership:
    base = Membership.create_active(
        id=MembershipId(uuid4()),
        tenant_id=TenantId(uuid4()),
        user_id=UserId(uuid4()),
        role=MembershipRole.MEMBER,
        created_at=_NOW,
    )
    return replace(base, role=role, status=status, version=version)


# --- status geçişleri --------------------------------------------------------


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        (MembershipStatus.ACTIVE, MembershipStatus.SUSPENDED),
        (MembershipStatus.SUSPENDED, MembershipStatus.ACTIVE),
        (MembershipStatus.ACTIVE, MembershipStatus.REMOVED),
        (MembershipStatus.SUSPENDED, MembershipStatus.REMOVED),
    ],
)
def test_allowed_status_transitions(src: MembershipStatus, dst: MembershipStatus) -> None:
    later = _NOW + timedelta(hours=1)
    updated = _membership(status=src).apply_management_change(
        new_role=None, new_status=dst, now=later
    )
    assert updated.status is dst
    assert updated.updated_at == later
    assert updated.version == 1  # CAS beklenen sürüm; repo artırır


@pytest.mark.parametrize(
    "dst", [MembershipStatus.ACTIVE, MembershipStatus.SUSPENDED, MembershipStatus.REMOVED]
)
def test_removed_is_terminal(dst: MembershipStatus) -> None:
    with pytest.raises(MembershipRemovedError):
        _membership(status=MembershipStatus.REMOVED).apply_management_change(
            new_role=None, new_status=dst, now=_NOW
        )


def test_removed_role_change_rejected() -> None:
    with pytest.raises(MembershipRemovedError):
        _membership(
            role=MembershipRole.MEMBER, status=MembershipStatus.REMOVED
        ).apply_management_change(new_role=MembershipRole.ADMIN, new_status=None, now=_NOW)


def test_role_change_applies() -> None:
    updated = _membership(role=MembershipRole.MEMBER).apply_management_change(
        new_role=MembershipRole.ADMIN, new_status=None, now=_NOW
    )
    assert updated.role is MembershipRole.ADMIN
    assert updated.status is MembershipStatus.ACTIVE


def test_role_and_status_change_together() -> None:
    updated = _membership(
        role=MembershipRole.MEMBER, status=MembershipStatus.ACTIVE
    ).apply_management_change(
        new_role=MembershipRole.ADMIN, new_status=MembershipStatus.SUSPENDED, now=_NOW
    )
    assert updated.role is MembershipRole.ADMIN and updated.status is MembershipStatus.SUSPENDED


def test_invalid_transition_would_raise_if_reachable() -> None:
    # removed dışı geçersiz bir geçiş kurgusu: active→invited gibi (invited settable değil,
    # ama apply doğrudan çağrılırsa izin listesi reddeder). invited→? kapsam dışı; burada
    # active→active no-op'tur (is_noop use-case'te), transition değil.
    with pytest.raises(InvalidMembershipTransitionError):
        _membership(status=MembershipStatus.ACTIVE).apply_management_change(
            new_role=None, new_status=MembershipStatus.INVITED, now=_NOW
        )


# --- owner invariant yardımcıları -------------------------------------------


def test_is_active_owner() -> None:
    assert _membership(role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE).is_active_owner()
    assert not _membership(
        role=MembershipRole.OWNER, status=MembershipStatus.SUSPENDED
    ).is_active_owner()
    assert not _membership(role=MembershipRole.ADMIN).is_active_owner()


def test_deactivates_owner() -> None:
    owner = _membership(role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE)
    assert owner.deactivates_owner(new_role=MembershipRole.ADMIN, new_status=None)
    assert owner.deactivates_owner(new_role=None, new_status=MembershipStatus.SUSPENDED)
    assert owner.deactivates_owner(new_role=None, new_status=MembershipStatus.REMOVED)
    assert not owner.deactivates_owner(new_role=MembershipRole.OWNER, new_status=None)
    assert not owner.deactivates_owner(new_role=None, new_status=None)
    # non-owner veya inaktif owner → deaktive etmez.
    assert not _membership(role=MembershipRole.MEMBER).deactivates_owner(
        new_role=MembershipRole.OWNER, new_status=None
    )


def test_is_noop() -> None:
    m = _membership(role=MembershipRole.MEMBER, status=MembershipStatus.ACTIVE)
    assert m.is_noop(new_role=MembershipRole.MEMBER, new_status=MembershipStatus.ACTIVE)
    assert m.is_noop(new_role=None, new_status=MembershipStatus.ACTIVE)
    assert not m.is_noop(new_role=MembershipRole.ADMIN, new_status=None)


# --- hedef-yetki policy ------------------------------------------------------


def test_owner_may_change_any_target() -> None:
    for target in (MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.MEMBER):
        for new in (None, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.MEMBER):
            authorize_member_change(actor_role="owner", target_role=target, new_role=new)


def test_admin_may_only_manage_member_and_not_grant_owner() -> None:
    authorize_member_change(
        actor_role="admin", target_role=MembershipRole.MEMBER, new_role=MembershipRole.ADMIN
    )
    authorize_member_change(actor_role="admin", target_role=MembershipRole.MEMBER, new_role=None)
    with pytest.raises(MemberManagementForbiddenError):
        authorize_member_change(
            actor_role="admin", target_role=MembershipRole.MEMBER, new_role=MembershipRole.OWNER
        )
    for target in (MembershipRole.OWNER, MembershipRole.ADMIN):
        with pytest.raises(MemberManagementForbiddenError):
            authorize_member_change(actor_role="admin", target_role=target, new_role=None)


def test_member_actor_forbidden() -> None:
    with pytest.raises(MemberManagementForbiddenError):
        authorize_member_change(
            actor_role="member", target_role=MembershipRole.MEMBER, new_role=None
        )
