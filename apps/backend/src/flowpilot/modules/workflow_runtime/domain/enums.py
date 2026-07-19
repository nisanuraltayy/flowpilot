"""Workflow Runtime durum ve node tipi enum'ları.

State machine kuralları domain-boundaries.md §5 ile hizalıdır. MVP node seti
YALNIZ 6 tiptir; bunun dışında node YAYINLANAMAZ (mvp-scope §2, FF-16).
"""

from __future__ import annotations

from enum import StrEnum


class WorkflowNodeType(StrEnum):
    """Gerçek MVP node seti (yalnız 6). Başka tip implemente/yayınlanamaz."""

    START = "start"
    FORM = "form"
    CONDITION = "condition"
    SEQUENTIAL_APPROVAL = "sequential_approval"
    NOTIFICATION = "notification"
    END = "end"


class WorkflowInstanceStatus(StrEnum):
    """Instance yaşam döngüsü (domain-boundaries.md §5).

    Terminal: completed, rejected, cancelled, failed.
    """

    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_INSTANCE_STATES


class WorkflowTaskStatus(StrEnum):
    """Human task / approval step durumu (domain-boundaries.md §5).

    Terminal: approved, rejected, changes_requested, cancelled.
    """

    PENDING = "pending"
    ACTIVE = "active"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_TASK_STATES


_TERMINAL_INSTANCE_STATES = frozenset(
    {
        WorkflowInstanceStatus.COMPLETED,
        WorkflowInstanceStatus.REJECTED,
        WorkflowInstanceStatus.CANCELLED,
        WorkflowInstanceStatus.FAILED,
    }
)

_TERMINAL_TASK_STATES = frozenset(
    {
        WorkflowTaskStatus.APPROVED,
        WorkflowTaskStatus.REJECTED,
        WorkflowTaskStatus.CHANGES_REQUESTED,
        WorkflowTaskStatus.CANCELLED,
    }
)
