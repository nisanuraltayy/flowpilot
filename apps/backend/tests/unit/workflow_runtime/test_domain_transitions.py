"""Instance/Task state machine: geçerli/terminal transition, sıra, duplicate (unit)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from flowpilot.modules.workflow_runtime.domain.enums import (
    WorkflowInstanceStatus,
    WorkflowTaskStatus,
)
from flowpilot.modules.workflow_runtime.domain.errors import (
    DuplicateDecisionError,
    InvalidTransitionError,
    SequenceOrderError,
    TerminalInstanceError,
    UnauthorizedApproverError,
)
from flowpilot.modules.workflow_runtime.domain.identifiers import (
    WorkflowDefinitionVersionId,
    WorkflowInstanceId,
    WorkflowTaskId,
)
from flowpilot.modules.workflow_runtime.domain.instance import WorkflowInstance
from flowpilot.modules.workflow_runtime.domain.task import WorkflowTask
from flowpilot.shared.identifiers import TenantId, UserId

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def _instance(status: WorkflowInstanceStatus, *, node: str = "approval") -> WorkflowInstance:
    return WorkflowInstance(
        id=WorkflowInstanceId(uuid4()),
        tenant_id=TenantId(uuid4()),
        definition_version_id=WorkflowDefinitionVersionId(uuid4()),
        definition_hash="h",
        status=status,
        current_node_id=node,
        context={},
        version=1,
    )


def _task(
    status: WorkflowTaskStatus, *, index: int = 0, role: str = "team_manager"
) -> WorkflowTask:
    return WorkflowTask(
        id=WorkflowTaskId(uuid4()),
        tenant_id=TenantId(uuid4()),
        instance_id=WorkflowInstanceId(uuid4()),
        node_id="approval",
        step_index=index,
        approver_role=role,
        status=status,
        version=1,
    )


@pytest.mark.parametrize(
    "status",
    [
        WorkflowInstanceStatus.COMPLETED,
        WorkflowInstanceStatus.REJECTED,
        WorkflowInstanceStatus.CANCELLED,
        WorkflowInstanceStatus.FAILED,
    ],
)
def test_terminal_instance_guard(status: WorkflowInstanceStatus) -> None:
    with pytest.raises(TerminalInstanceError):
        _instance(status).guard_not_terminal()


def test_waiting_can_complete_and_bumps_version() -> None:
    instance = _instance(WorkflowInstanceStatus.WAITING)
    completed = instance.complete(node_id="end", now=NOW)
    assert completed.status is WorkflowInstanceStatus.COMPLETED
    assert completed.version == 2
    assert instance.status is WorkflowInstanceStatus.WAITING  # immutable — orijinal değişmez


def test_terminal_instance_cannot_transition() -> None:
    with pytest.raises(TerminalInstanceError):
        _instance(WorkflowInstanceStatus.COMPLETED).complete(node_id="end", now=NOW)


def test_pending_task_cannot_be_decided() -> None:
    with pytest.raises(SequenceOrderError):
        _task(WorkflowTaskStatus.PENDING).decide(
            actor=UserId(uuid4()),
            approver_role="team_manager",
            decision=WorkflowTaskStatus.APPROVED,
            idempotency_key="k",
        )


def test_wrong_role_rejected() -> None:
    with pytest.raises(UnauthorizedApproverError):
        _task(WorkflowTaskStatus.ACTIVE, role="finance").decide(
            actor=UserId(uuid4()),
            approver_role="team_manager",
            decision=WorkflowTaskStatus.APPROVED,
            idempotency_key="k",
        )


def test_active_task_approves() -> None:
    actor = UserId(uuid4())
    decided = _task(WorkflowTaskStatus.ACTIVE).decide(
        actor=actor,
        approver_role="team_manager",
        decision=WorkflowTaskStatus.APPROVED,
        idempotency_key="k",
    )
    assert decided.status is WorkflowTaskStatus.APPROVED
    assert decided.decided_by == actor
    assert decided.version == 2


def test_idempotent_replay_same_actor_same_key() -> None:
    actor = UserId(uuid4())
    task = _task(WorkflowTaskStatus.ACTIVE)
    first = task.decide(
        actor=actor,
        approver_role="team_manager",
        decision=WorkflowTaskStatus.APPROVED,
        idempotency_key="k",
    )
    replay = first.decide(
        actor=actor,
        approver_role="team_manager",
        decision=WorkflowTaskStatus.APPROVED,
        idempotency_key="k",
    )
    assert replay is first  # yeni karar üretmez


def test_duplicate_decision_different_actor_rejected() -> None:
    task = _task(WorkflowTaskStatus.ACTIVE)
    decided = task.decide(
        actor=UserId(uuid4()),
        approver_role="team_manager",
        decision=WorkflowTaskStatus.APPROVED,
        idempotency_key="k1",
    )
    with pytest.raises(DuplicateDecisionError):
        decided.decide(
            actor=UserId(uuid4()),
            approver_role="team_manager",
            decision=WorkflowTaskStatus.REJECTED,
            idempotency_key="k2",
        )


def test_invalid_decision_value_rejected() -> None:
    with pytest.raises(InvalidTransitionError):
        _task(WorkflowTaskStatus.ACTIVE).decide(
            actor=UserId(uuid4()),
            approver_role="team_manager",
            decision=WorkflowTaskStatus.PENDING,
            idempotency_key="k",
        )


def test_pending_activates() -> None:
    activated = _task(WorkflowTaskStatus.PENDING, index=1).activate(now=NOW)
    assert activated.status is WorkflowTaskStatus.ACTIVE
    assert activated.version == 2
