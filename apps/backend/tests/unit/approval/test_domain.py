"""Approval domain birim testleri: role key allow-list, comment VO, assignment."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from flowpilot.modules.approval.domain.enums import (
    ALL_ROLE_KEYS,
    ApprovalDecisionType,
    ApprovalRoleKey,
)
from flowpilot.modules.approval.domain.errors import InvalidApprovalCommentError
from flowpilot.modules.approval.domain.models import (
    ApprovalComment,
    ApprovalRoleAssignment,
    ApprovalRoleAssignmentId,
)
from flowpilot.shared.identifiers import TenantId, UserId

_NOW = datetime(2026, 7, 19, tzinfo=UTC)


def test_role_keys_are_exactly_three_owner_approved() -> None:
    assert ALL_ROLE_KEYS == (
        ApprovalRoleKey.TEAM_MANAGER,
        ApprovalRoleKey.FINANCE,
        ApprovalRoleKey.GENERAL_MANAGER,
    )


def test_decision_type_allow_list() -> None:
    assert {d.value for d in ApprovalDecisionType} == {"approve", "reject"}


def test_comment_none_and_blank_normalize_to_none() -> None:
    assert ApprovalComment(None).value is None
    assert ApprovalComment("   ").value is None


def test_comment_trimmed_and_bounded() -> None:
    assert ApprovalComment("  onaylandı  ").value == "onaylandı"
    ApprovalComment("x" * 2000)  # sınırda kabul
    with pytest.raises(InvalidApprovalCommentError):
        ApprovalComment("x" * 2001)


def test_create_active_assignment_is_active() -> None:
    assignment = ApprovalRoleAssignment.create_active(
        id=ApprovalRoleAssignmentId(uuid4()),
        tenant_id=TenantId(uuid4()),
        role_key=ApprovalRoleKey.FINANCE,
        assigned_user_id=UserId(uuid4()),
        created_at=_NOW,
    )
    assert assignment.status.value == "active"
    assert assignment.role_key is ApprovalRoleKey.FINANCE
    assert assignment.created_at == assignment.updated_at == _NOW
