"""Typed command ve result/view sözleşmeleri (provider-neutral).

Bu DTO'lar `WorkflowRuntimePort`'un girdi/çıktısıdır. SQLAlchemy model, session
veya ORM tipi İÇERMEZ — yalnız primitive'ler ve domain value object'leri.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

# --------------------------------------------------------------------- komutlar


@dataclass(frozen=True)
class PublishDefinitionCommand:
    tenant_id: UUID
    actor_user_id: UUID
    definition_key: str
    definition: dict[str, Any]
    request_id: str


@dataclass(frozen=True)
class StartInstanceCommand:
    tenant_id: UUID
    actor_user_id: UUID
    definition_version_id: UUID
    request_id: str
    initial_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubmitFormCommand:
    tenant_id: UUID
    actor_user_id: UUID
    instance_id: UUID
    expected_version: int
    form_data: dict[str, Any]
    request_id: str
    # role_key → assigned user_id (str). Approval task'ları oluşturulurken assignee
    # SABİTLENİR (owner #5). Boş bırakılırsa assignee None (assignee-öncesi testler).
    role_assignees: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DecideTaskCommand:
    tenant_id: UUID
    actor_user_id: UUID
    task_id: UUID
    approver_role: str
    decision: str  # "approved" | "rejected"
    idempotency_key: str
    request_id: str


@dataclass(frozen=True)
class CancelInstanceCommand:
    tenant_id: UUID
    actor_user_id: UUID
    instance_id: UUID
    expected_version: int
    request_id: str


@dataclass(frozen=True)
class ScheduleTimerCommand:
    tenant_id: UUID
    instance_id: UUID
    purpose: str
    fire_at: datetime


# ----------------------------------------------------------------- result/views


@dataclass(frozen=True)
class PublishDefinitionResult:
    definition_id: UUID
    definition_version_id: UUID
    version_no: int
    content_hash: str


@dataclass(frozen=True)
class TaskView:
    task_id: UUID
    node_id: str
    step_index: int
    approver_role: str
    status: str
    assigned_user_id: UUID | None = None
    blocked_reason: str | None = None


@dataclass(frozen=True)
class InstanceView:
    instance_id: UUID
    definition_version_id: UUID
    definition_hash: str
    status: str
    current_node_id: str
    version: int
    branch_explanation: str | None = None
    active_task: TaskView | None = None
    # İlk adım self-approval nedeniyle blocked ise (active_task None), baş adım burada döner.
    blocked_task: TaskView | None = None


@dataclass(frozen=True)
class DecisionResult:
    task_id: UUID
    step_index: int
    instance_id: UUID
    decision: str
    duplicate: bool
    instance_status: str
    activated_task_id: UUID | None
    required_role: str | None = None
    next_approval_role: str | None = None
    next_task_assigned_user_id: UUID | None = None
    # Onay sonrası sıradaki adım self-approval nedeniyle blocked olduysa (activate → blocked).
    blocked_task_id: UUID | None = None
    blocked_role: str | None = None


@dataclass(frozen=True)
class ResolveAssignmentResult:
    task_id: UUID
    instance_id: UUID
    step_index: int
    approver_role: str
    status: str
    assigned_user_id: UUID
    version: int
    purchase_request_id: UUID | None = None


@dataclass(frozen=True)
class TimelineEntry:
    event_id: UUID
    event_type: str
    node_id: str | None
    actor_type: str
    occurred_at: datetime
    detail: dict[str, Any]


@dataclass(frozen=True)
class DispatchStats:
    """Bir dispatcher turunun sonucu (gözlemlenebilirlik + test)."""

    fired_timers: int = 0
    processed: int = 0
    duplicate: int = 0
    retried: int = 0
    failed: int = 0
