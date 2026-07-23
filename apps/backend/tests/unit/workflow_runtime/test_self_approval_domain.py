"""Self-approval domain birim testleri (FP-E06-009) — blocked geçişleri + resolve."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from flowpilot.modules.workflow_runtime.domain.enums import WorkflowTaskStatus
from flowpilot.modules.workflow_runtime.domain.errors import (
    SequenceOrderError,
    TaskNotBlockedError,
)
from flowpilot.modules.workflow_runtime.domain.identifiers import (
    WorkflowInstanceId,
    WorkflowTaskId,
)
from flowpilot.modules.workflow_runtime.domain.task import (
    SELF_APPROVAL_BLOCKED_REASON,
    WorkflowTask,
)
from flowpilot.shared.identifiers import TenantId, UserId

_NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
_LATER = datetime(2026, 7, 21, 13, 0, tzinfo=UTC)


def _task(
    *,
    status: WorkflowTaskStatus,
    index: int = 0,
    assignee: UserId | None = None,
    blocked_reason: str | None = None,
) -> WorkflowTask:
    return WorkflowTask(
        id=WorkflowTaskId(uuid4()),
        tenant_id=TenantId(uuid4()),
        instance_id=WorkflowInstanceId(uuid4()),
        node_id="approval",
        step_index=index,
        approver_role="finance",
        status=status,
        version=1,
        assigned_user_id=assignee,
        blocked_reason=blocked_reason,
    )


def test_activate_normal_pending_becomes_active() -> None:
    activated = _task(status=WorkflowTaskStatus.PENDING, index=1).activate(now=_NOW)
    assert activated.status is WorkflowTaskStatus.ACTIVE
    assert activated.version == 2 and activated.blocked_at is None


def test_activate_self_conflict_pending_becomes_blocked() -> None:
    task = _task(
        status=WorkflowTaskStatus.PENDING, index=1, blocked_reason=SELF_APPROVAL_BLOCKED_REASON
    )
    assert task.is_self_conflict
    activated = task.activate(now=_NOW)
    assert activated.status is WorkflowTaskStatus.BLOCKED
    assert activated.blocked_at == _NOW and activated.version == 2
    assert activated.blocked_reason == SELF_APPROVAL_BLOCKED_REASON


def test_blocked_task_cannot_be_decided() -> None:
    blocked = _task(status=WorkflowTaskStatus.BLOCKED, blocked_reason=SELF_APPROVAL_BLOCKED_REASON)
    with pytest.raises(SequenceOrderError):
        blocked.decide(
            actor=UserId(uuid4()),
            approver_role="finance",
            decision=WorkflowTaskStatus.APPROVED,
            idempotency_key="k",
        )


def test_resolve_assignment_blocked_to_active() -> None:
    new_user = UserId(uuid4())
    blocked = _task(status=WorkflowTaskStatus.BLOCKED, blocked_reason=SELF_APPROVAL_BLOCKED_REASON)
    resolved = blocked.resolve_assignment(new_assignee=new_user, now=_LATER)
    assert resolved.status is WorkflowTaskStatus.ACTIVE
    assert resolved.assigned_user_id == new_user
    assert resolved.blocked_reason is None and resolved.blocked_at is None
    assert resolved.version == 2


def test_resolve_assignment_on_active_task_rejected() -> None:
    active = _task(status=WorkflowTaskStatus.ACTIVE, assignee=UserId(uuid4()))
    with pytest.raises(TaskNotBlockedError):
        active.resolve_assignment(new_assignee=UserId(uuid4()), now=_LATER)


def test_resolve_assignment_on_blocked_without_self_reason_rejected() -> None:
    # blocked ama self-approval reason'ı yoksa resolve edilemez (savunmacı).
    blocked = _task(status=WorkflowTaskStatus.BLOCKED, blocked_reason=None)
    with pytest.raises(TaskNotBlockedError):
        blocked.resolve_assignment(new_assignee=UserId(uuid4()), now=_LATER)


def test_activated_blocked_not_terminal() -> None:
    assert WorkflowTaskStatus.BLOCKED.is_terminal is False
