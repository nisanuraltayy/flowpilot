"""Merkezi authorization policy — davet yönetimi izinleri (FP-E03-001)."""

from __future__ import annotations

import pytest

from flowpilot.modules.authorization.application.access import (
    Permission,
    PermissionDeniedError,
    ensure_permitted,
    is_authorized,
    permissions_for_role,
)

_INVITATION_PERMISSIONS = [
    Permission.ORGANIZATION_INVITATION_CREATE,
    Permission.ORGANIZATION_INVITATION_READ,
    Permission.ORGANIZATION_INVITATION_REVOKE,
]


@pytest.mark.parametrize("role", ["owner", "admin"])
@pytest.mark.parametrize("permission", _INVITATION_PERMISSIONS)
def test_owner_and_admin_can_manage_invitations(role: str, permission: Permission) -> None:
    assert is_authorized(role=role, permission=permission) is True
    ensure_permitted(role=role, permission=permission)  # no raise


@pytest.mark.parametrize("permission", _INVITATION_PERMISSIONS)
def test_member_cannot_manage_invitations(permission: Permission) -> None:
    assert is_authorized(role="member", permission=permission) is False
    with pytest.raises(PermissionDeniedError):
        ensure_permitted(role="member", permission=permission)


@pytest.mark.parametrize("permission", _INVITATION_PERMISSIONS)
def test_unknown_role_denied(permission: Permission) -> None:
    assert is_authorized(role="", permission=permission) is False
    assert is_authorized(role="superadmin", permission=permission) is False
    with pytest.raises(PermissionDeniedError):
        ensure_permitted(role="superadmin", permission=permission)


_MEMBER_MGMT_PERMISSIONS = [
    Permission.ORGANIZATION_MEMBER_READ,
    Permission.ORGANIZATION_MEMBER_ROLE_CHANGE,
    Permission.ORGANIZATION_MEMBER_SUSPEND,
    Permission.ORGANIZATION_MEMBER_REACTIVATE,
    Permission.ORGANIZATION_MEMBER_REMOVE,
]

_APPROVAL_ROLE_PERMISSIONS = [
    Permission.APPROVAL_ROLE_ASSIGNMENT_READ,
    Permission.APPROVAL_ROLE_ASSIGNMENT_CHANGE,
]


@pytest.mark.parametrize("role", ["owner", "admin"])
@pytest.mark.parametrize("permission", _APPROVAL_ROLE_PERMISSIONS)
def test_owner_and_admin_can_manage_approval_roles(role: str, permission: Permission) -> None:
    assert is_authorized(role=role, permission=permission) is True


@pytest.mark.parametrize("permission", _APPROVAL_ROLE_PERMISSIONS)
def test_member_cannot_manage_approval_roles(permission: Permission) -> None:
    assert is_authorized(role="member", permission=permission) is False


def test_member_has_no_permissions_and_owner_has_all() -> None:
    assert permissions_for_role("member") == frozenset()
    expected = frozenset(
        _INVITATION_PERMISSIONS + _MEMBER_MGMT_PERMISSIONS + _APPROVAL_ROLE_PERMISSIONS
    )
    assert permissions_for_role("owner") == expected
    assert permissions_for_role("admin") == expected
