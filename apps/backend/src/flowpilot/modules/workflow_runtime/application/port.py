"""WorkflowRuntimePort (capability sözleşmesi) + repository/UnitOfWork port'ları.

`WorkflowRuntimePort` uygulamanın geri kalanının (API, worker, purchase_request)
gördüğü provider-neutral yüzeydir. Somut runtime sınıfları GİZLİDİR; port
SQLAlchemy model/session döndürmez. Repository ve UnitOfWork port'ları, servisin
infrastructure'dan ihtiyaç duyduğu yeteneklerdir (aggregate-specific; generic
repository YASAK).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, Protocol
from uuid import UUID

from flowpilot.modules.workflow_runtime.application.dto import (
    CancelInstanceCommand,
    DecideTaskCommand,
    DecisionResult,
    DispatchStats,
    InstanceView,
    PublishDefinitionCommand,
    PublishDefinitionResult,
    ScheduleTimerCommand,
    StartInstanceCommand,
    SubmitFormCommand,
    TimelineEntry,
)
from flowpilot.modules.workflow_runtime.domain.definition import WorkflowDefinitionVersion
from flowpilot.modules.workflow_runtime.domain.event import IntegrationEvent, WorkflowEvent
from flowpilot.modules.workflow_runtime.domain.instance import WorkflowInstance
from flowpilot.modules.workflow_runtime.domain.task import WorkflowTask

# --------------------------------------------------- infra'dan dönen okuma tipleri


@dataclass(frozen=True)
class ClaimedOutboxEvent:
    outbox_id: int
    event_id: UUID
    tenant_id: UUID
    event_type: str
    payload: dict[str, Any]
    attempt: int


@dataclass(frozen=True)
class ClaimedTimer:
    timer_id: UUID
    tenant_id: UUID
    instance_id: UUID
    purpose: str


# ----------------------------------------------------------- repository port'ları


class DefinitionRepository(Protocol):
    def add_version(
        self, version: WorkflowDefinitionVersion, *, tenant_id: UUID, published_at: datetime
    ) -> None: ...

    def ensure_definition(
        self, *, tenant_id: UUID, definition_id: UUID, definition_key: str, created_at: datetime
    ) -> UUID:
        """definition_key için mevcut definition id'yi döndürür; yoksa oluşturur."""
        ...

    def get_version(self, version_id: UUID) -> WorkflowDefinitionVersion: ...


class InstanceRepository(Protocol):
    def add(self, instance: WorkflowInstance, *, now: datetime) -> None: ...

    def get(self, instance_id: UUID) -> WorkflowInstance: ...

    def update_checked(
        self, instance: WorkflowInstance, *, expected_version: int, now: datetime
    ) -> None:
        """Optimistic CAS: expected_version tutmazsa ConcurrencyConflictError."""
        ...


class TaskRepository(Protocol):
    def add(self, task: WorkflowTask, *, now: datetime) -> None: ...

    def get(self, task_id: UUID) -> WorkflowTask: ...

    def list_for_instance(self, instance_id: UUID) -> list[WorkflowTask]: ...

    def find_by_step(self, instance_id: UUID, step_index: int) -> WorkflowTask | None: ...

    def update_checked(
        self, task: WorkflowTask, *, expected_version: int, now: datetime
    ) -> None: ...

    def cancel_open_for_instance(self, instance_id: UUID, *, now: datetime) -> None: ...


class EventLog(Protocol):
    def append(self, event: WorkflowEvent) -> None: ...

    def list_for_instance(self, instance_id: UUID) -> list[TimelineEntry]: ...

    def count_for_instance(self, instance_id: UUID) -> int: ...


class OutboxStore(Protocol):
    def enqueue(self, event: IntegrationEvent, *, created_at: datetime) -> None: ...

    def claim_due(
        self, *, worker_id: str, now: datetime, lease_seconds: float, limit: int
    ) -> list[ClaimedOutboxEvent]:
        """FOR UPDATE SKIP LOCKED ile vadesi gelmiş event'leri kilitler + lease yazar."""
        ...

    def mark_processed(self, outbox_id: int, *, now: datetime) -> None: ...

    def mark_retry_or_failed(self, event: ClaimedOutboxEvent, *, now: datetime, error: str) -> str:
        """Bounded retry: backoff ile yeniden dener; limitte 'failed'. Dönen: outcome."""
        ...


class InboxStore(Protocol):
    def mark_if_new(self, event_id: UUID, *, consumer: str, tenant_id: UUID, now: datetime) -> bool:
        """İlk kez ise True (INSERT); daha önce işlenmişse False (duplicate)."""
        ...


class TimerStore(Protocol):
    def schedule(self, command: ScheduleTimerCommand, *, timer_id: UUID, now: datetime) -> UUID: ...

    def claim_due(self, *, now: datetime, limit: int) -> list[ClaimedTimer]: ...

    def mark_fired(self, timer_id: UUID, *, worker_id: str, now: datetime) -> bool: ...

    def cancel_open_for_instance(self, instance_id: UUID) -> None: ...


class WorkflowUnitOfWork(Protocol):
    """Tek transaction + RLS context yönetimi; repository'ler attribute olarak.

    Transaction sınırı BURADADIR — repository/adapter içinden rastgele commit
    YASAK. State + task + event + outbox aynı `with uow:` bloğunda yazılır.
    """

    definitions: DefinitionRepository
    instances: InstanceRepository
    tasks: TaskRepository
    events: EventLog
    outbox: OutboxStore
    inbox: InboxStore
    timers: TimerStore

    def __enter__(self) -> WorkflowUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def set_tenant_context(self, tenant_id: UUID) -> None: ...

    def set_actor_context(self, actor_user_id: UUID) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


# ----------------------------------------------------- capability facade (port)


class WorkflowRuntimePort(Protocol):
    """Uygulamanın geri kalanının gördüğü provider-neutral runtime sözleşmesi."""

    def publish_definition(self, command: PublishDefinitionCommand) -> PublishDefinitionResult: ...

    def start_instance(self, command: StartInstanceCommand) -> InstanceView: ...

    def load_instance(self, *, tenant_id: UUID, instance_id: UUID) -> InstanceView: ...

    def submit_form(self, command: SubmitFormCommand) -> InstanceView: ...

    def decide_task(self, command: DecideTaskCommand) -> DecisionResult: ...

    def cancel_instance(self, command: CancelInstanceCommand) -> None: ...

    def schedule_timer(self, command: ScheduleTimerCommand) -> UUID: ...

    def get_timeline(self, *, tenant_id: UUID, instance_id: UUID) -> list[TimelineEntry]: ...

    def run_dispatch_pass(
        self, *, tenant_id: UUID, worker_id: str, now: datetime | None = None, limit: int = 20
    ) -> DispatchStats: ...
