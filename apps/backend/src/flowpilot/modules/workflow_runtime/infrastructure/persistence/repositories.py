"""SQLAlchemy Core tabanlı aggregate-specific repository'ler.

Her repository bir port'u uygular; domain ↔ satır eşlemesi burada yapılır (domain
SQLAlchemy bilmez). Adapter'lar COMMIT ETMEZ — transaction sınırı UnitOfWork'tedir.
Yazma metodları `flush()` eder (RLS/constraint erken değerlendirilsin). `get`,
kayıt yoksa VEYA RLS erişimi keserse aynı NotFound'u üretir (varlık sızmaz).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, and_, insert, select, text, update
from sqlalchemy.orm import Session

from flowpilot.modules.workflow_runtime.application.dto import (
    ScheduleTimerCommand,
    TimelineEntry,
)
from flowpilot.modules.workflow_runtime.application.port import (
    ClaimedOutboxEvent,
    ClaimedTimer,
)
from flowpilot.modules.workflow_runtime.domain.definition import WorkflowDefinitionVersion
from flowpilot.modules.workflow_runtime.domain.enums import (
    WorkflowInstanceStatus,
    WorkflowTaskStatus,
)
from flowpilot.modules.workflow_runtime.domain.errors import (
    ConcurrencyConflictError,
    DefinitionVersionNotFoundError,
    WorkflowInstanceNotFoundError,
    WorkflowTaskNotFoundError,
)
from flowpilot.modules.workflow_runtime.domain.event import IntegrationEvent, WorkflowEvent
from flowpilot.modules.workflow_runtime.domain.identifiers import (
    WorkflowDefinitionId,
    WorkflowDefinitionVersionId,
    WorkflowInstanceId,
    WorkflowTaskId,
)
from flowpilot.modules.workflow_runtime.domain.instance import WorkflowInstance
from flowpilot.modules.workflow_runtime.domain.task import WorkflowTask
from flowpilot.modules.workflow_runtime.infrastructure.persistence.tables import (
    definition_versions_table,
    definitions_table,
    events_table,
    instances_table,
    outbox_table,
    tasks_table,
    timers_table,
)
from flowpilot.shared.identifiers import TenantId, UserId

MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 0.05


def _rowcount(result: object) -> int:
    return int(cast(CursorResult[Any], result).rowcount)


class SqlAlchemyDefinitionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_definition(
        self, *, tenant_id: UUID, definition_id: UUID, definition_key: str, created_at: datetime
    ) -> UUID:
        existing = self._session.execute(
            select(definitions_table.c.id).where(
                definitions_table.c.definition_key == definition_key
            )
        ).first()
        if existing is not None:
            return cast(UUID, existing[0])
        self._session.execute(
            insert(definitions_table).values(
                id=definition_id,
                tenant_id=tenant_id,
                definition_key=definition_key,
                created_at=created_at,
            )
        )
        self._session.flush()
        return definition_id

    def add_version(
        self, version: WorkflowDefinitionVersion, *, tenant_id: UUID, published_at: datetime
    ) -> None:
        self._session.execute(
            insert(definition_versions_table).values(
                id=version.id.value,
                tenant_id=tenant_id,
                definition_id=version.definition_id.value,
                version_no=version.version_no,
                definition=version.definition,
                content_hash=version.content_hash,
                published_at=published_at,
            )
        )
        self._session.flush()

    def get_version(self, version_id: UUID) -> WorkflowDefinitionVersion:
        row = (
            self._session.execute(
                select(
                    definition_versions_table.c.id,
                    definition_versions_table.c.definition_id,
                    definition_versions_table.c.version_no,
                    definition_versions_table.c.definition,
                    definition_versions_table.c.content_hash,
                ).where(definition_versions_table.c.id == version_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise DefinitionVersionNotFoundError("workflow definition version bulunamadı")
        return WorkflowDefinitionVersion(
            id=WorkflowDefinitionVersionId(row["id"]),
            definition_id=WorkflowDefinitionId(row["definition_id"]),
            version_no=int(row["version_no"]),
            definition=cast(dict[str, Any], row["definition"]),
            content_hash=str(row["content_hash"]),
        )


class SqlAlchemyInstanceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, instance: WorkflowInstance, *, now: datetime) -> None:
        self._session.execute(
            insert(instances_table).values(
                id=instance.id.value,
                tenant_id=instance.tenant_id.value,
                definition_version_id=instance.definition_version_id.value,
                definition_hash=instance.definition_hash,
                status=instance.status.value,
                current_node_id=instance.current_node_id,
                context=instance.context,
                version=instance.version,
                created_at=now,
                updated_at=now,
            )
        )
        self._session.flush()

    def get(self, instance_id: UUID) -> WorkflowInstance:
        row = (
            self._session.execute(
                select(instances_table).where(instances_table.c.id == instance_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowInstanceNotFoundError("workflow instance bulunamadı")
        return WorkflowInstance(
            id=WorkflowInstanceId(row["id"]),
            tenant_id=TenantId(row["tenant_id"]),
            definition_version_id=WorkflowDefinitionVersionId(row["definition_version_id"]),
            definition_hash=str(row["definition_hash"]),
            status=WorkflowInstanceStatus(row["status"]),
            current_node_id=str(row["current_node_id"]),
            context=cast(dict[str, Any], row["context"]),
            version=int(row["version"]),
        )

    def update_checked(
        self, instance: WorkflowInstance, *, expected_version: int, now: datetime
    ) -> None:
        result = self._session.execute(
            update(instances_table)
            .where(
                and_(
                    instances_table.c.id == instance.id.value,
                    instances_table.c.version == expected_version,
                )
            )
            .values(
                status=instance.status.value,
                current_node_id=instance.current_node_id,
                context=instance.context,
                version=instance.version,
                updated_at=now,
            )
        )
        if _rowcount(result) != 1:
            raise ConcurrencyConflictError(
                "instance eşzamanlı değişti — 409/412 (sessiz overwrite yok)"
            )


class SqlAlchemyTaskRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, task: WorkflowTask, *, now: datetime) -> None:
        self._session.execute(
            insert(tasks_table).values(
                id=task.id.value,
                tenant_id=task.tenant_id.value,
                instance_id=task.instance_id.value,
                node_id=task.node_id,
                step_index=task.step_index,
                approver_role=task.approver_role,
                status=task.status.value,
                version=task.version,
                created_at=now,
                updated_at=now,
            )
        )
        self._session.flush()

    def _map(self, row: dict[str, Any]) -> WorkflowTask:
        return WorkflowTask(
            id=WorkflowTaskId(row["id"]),
            tenant_id=TenantId(row["tenant_id"]),
            instance_id=WorkflowInstanceId(row["instance_id"]),
            node_id=str(row["node_id"]),
            step_index=int(row["step_index"]),
            approver_role=str(row["approver_role"]),
            status=WorkflowTaskStatus(row["status"]),
            version=int(row["version"]),
            decided_by=UserId(row["decided_by_user_id"]) if row["decided_by_user_id"] else None,
            decision=WorkflowTaskStatus(row["decision"]) if row["decision"] else None,
            idempotency_key=row["idempotency_key"],
        )

    def get(self, task_id: UUID) -> WorkflowTask:
        row = (
            self._session.execute(select(tasks_table).where(tasks_table.c.id == task_id))
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowTaskNotFoundError("workflow task bulunamadı")
        return self._map(dict(row))

    def list_for_instance(self, instance_id: UUID) -> list[WorkflowTask]:
        rows = (
            self._session.execute(
                select(tasks_table)
                .where(tasks_table.c.instance_id == instance_id)
                .order_by(tasks_table.c.step_index)
            )
            .mappings()
            .all()
        )
        return [self._map(dict(row)) for row in rows]

    def find_by_step(self, instance_id: UUID, step_index: int) -> WorkflowTask | None:
        row = (
            self._session.execute(
                select(tasks_table).where(
                    and_(
                        tasks_table.c.instance_id == instance_id,
                        tasks_table.c.step_index == step_index,
                    )
                )
            )
            .mappings()
            .first()
        )
        return self._map(dict(row)) if row is not None else None

    def update_checked(self, task: WorkflowTask, *, expected_version: int, now: datetime) -> None:
        result = self._session.execute(
            update(tasks_table)
            .where(
                and_(
                    tasks_table.c.id == task.id.value,
                    tasks_table.c.version == expected_version,
                )
            )
            .values(
                status=task.status.value,
                decided_by_user_id=task.decided_by.value if task.decided_by else None,
                decision=task.decision.value if task.decision else None,
                idempotency_key=task.idempotency_key,
                version=task.version,
                updated_at=now,
            )
        )
        if _rowcount(result) != 1:
            raise ConcurrencyConflictError("task eşzamanlı değişti — 409/412")

    def cancel_open_for_instance(self, instance_id: UUID, *, now: datetime) -> None:
        self._session.execute(
            update(tasks_table)
            .where(
                and_(
                    tasks_table.c.instance_id == instance_id,
                    tasks_table.c.status.in_(("pending", "active")),
                )
            )
            .values(status="cancelled", version=tasks_table.c.version + 1, updated_at=now)
        )


class SqlAlchemyEventLog:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: WorkflowEvent) -> None:
        self._session.execute(
            insert(events_table).values(
                id=event.id.value,
                tenant_id=event.tenant_id.value,
                instance_id=event.instance_id.value,
                event_type=event.event_type,
                node_id=event.node_id,
                actor_type=event.actor_type,
                detail=event.detail,
                occurred_at=event.occurred_at,
            )
        )
        self._session.flush()

    def list_for_instance(self, instance_id: UUID) -> list[TimelineEntry]:
        rows = (
            self._session.execute(
                select(events_table)
                .where(events_table.c.instance_id == instance_id)
                .order_by(events_table.c.occurred_at, events_table.c.id)
            )
            .mappings()
            .all()
        )
        return [
            TimelineEntry(
                event_id=row["id"],
                event_type=str(row["event_type"]),
                node_id=row["node_id"],
                actor_type=str(row["actor_type"]),
                occurred_at=row["occurred_at"],
                detail=cast(dict[str, Any], row["detail"]),
            )
            for row in rows
        ]

    def count_for_instance(self, instance_id: UUID) -> int:
        return len(self.list_for_instance(instance_id))


class SqlAlchemyOutboxStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(self, event: IntegrationEvent, *, created_at: datetime) -> None:
        self._session.execute(
            insert(outbox_table).values(
                tenant_id=event.tenant_id.value,
                event_id=event.id.value,
                event_type=event.event_type,
                payload=event.payload,
                available_at=event.available_at,
                created_at=created_at,
            )
        )
        self._session.flush()

    def claim_due(
        self, *, worker_id: str, now: datetime, lease_seconds: float, limit: int
    ) -> list[ClaimedOutboxEvent]:
        rows = (
            self._session.execute(
                text(
                    "SELECT id, tenant_id, event_id, event_type, payload, attempt "
                    "FROM workflow_runtime_outbox "
                    "WHERE status = 'pending' AND available_at <= :now "
                    "AND (claim_expires_at IS NULL OR claim_expires_at <= :now) "
                    "ORDER BY id LIMIT :limit FOR UPDATE SKIP LOCKED"
                ),
                {"now": now, "limit": limit},
            )
            .mappings()
            .all()
        )
        if not rows:
            return []
        ids = [int(row["id"]) for row in rows]
        self._session.execute(
            update(outbox_table)
            .where(outbox_table.c.id.in_(ids))
            .values(
                claimed_by=worker_id,
                claim_expires_at=now + timedelta(seconds=lease_seconds),
            )
        )
        return [
            ClaimedOutboxEvent(
                outbox_id=int(row["id"]),
                event_id=row["event_id"],
                tenant_id=row["tenant_id"],
                event_type=str(row["event_type"]),
                payload=cast(dict[str, Any], row["payload"]),
                attempt=int(row["attempt"]),
            )
            for row in rows
        ]

    def mark_processed(self, outbox_id: int, *, now: datetime) -> None:
        self._session.execute(
            update(outbox_table)
            .where(outbox_table.c.id == outbox_id)
            .values(status="processed", processed_at=now, claimed_by=None, claim_expires_at=None)
        )

    def mark_retry_or_failed(self, event: ClaimedOutboxEvent, *, now: datetime, error: str) -> str:
        next_attempt = event.attempt + 1
        if next_attempt >= MAX_ATTEMPTS:
            self._session.execute(
                update(outbox_table)
                .where(outbox_table.c.id == event.outbox_id)
                .values(
                    status="failed",
                    attempt=next_attempt,
                    claimed_by=None,
                    claim_expires_at=None,
                )
            )
            return "failed"
        backoff = BACKOFF_BASE_SECONDS * (2**next_attempt)
        self._session.execute(
            update(outbox_table)
            .where(outbox_table.c.id == event.outbox_id)
            .values(
                attempt=next_attempt,
                available_at=now + timedelta(seconds=backoff),
                claimed_by=None,
                claim_expires_at=None,
            )
        )
        return "retry"


class SqlAlchemyInboxStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def mark_if_new(self, event_id: UUID, *, consumer: str, tenant_id: UUID, now: datetime) -> bool:
        result = self._session.execute(
            text(
                "INSERT INTO workflow_runtime_inbox (event_id, consumer, tenant_id, processed_at) "
                "VALUES (:event_id, :consumer, :tenant_id, :now) ON CONFLICT DO NOTHING"
            ),
            {
                "event_id": str(event_id),
                "consumer": consumer,
                "tenant_id": str(tenant_id),
                "now": now,
            },
        )
        return _rowcount(result) == 1


class SqlAlchemyTimerStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def schedule(self, command: ScheduleTimerCommand, *, timer_id: UUID, now: datetime) -> UUID:
        self._session.execute(
            insert(timers_table).values(
                id=timer_id,
                tenant_id=command.tenant_id,
                instance_id=command.instance_id,
                purpose=command.purpose,
                fire_at=command.fire_at,
                created_at=now,
            )
        )
        self._session.flush()
        return timer_id

    def claim_due(self, *, now: datetime, limit: int) -> list[ClaimedTimer]:
        rows = (
            self._session.execute(
                text(
                    "SELECT id, tenant_id, instance_id, purpose FROM workflow_runtime_timers "
                    "WHERE status = 'pending' AND fire_at <= :now "
                    "ORDER BY fire_at LIMIT :limit FOR UPDATE SKIP LOCKED"
                ),
                {"now": now, "limit": limit},
            )
            .mappings()
            .all()
        )
        return [
            ClaimedTimer(
                timer_id=row["id"],
                tenant_id=row["tenant_id"],
                instance_id=row["instance_id"],
                purpose=str(row["purpose"]),
            )
            for row in rows
        ]

    def mark_fired(self, timer_id: UUID, *, worker_id: str, now: datetime) -> bool:
        result = self._session.execute(
            update(timers_table)
            .where(and_(timers_table.c.id == timer_id, timers_table.c.status == "pending"))
            .values(status="fired", fired_at=now, fired_by=worker_id)
        )
        return _rowcount(result) == 1

    def cancel_open_for_instance(self, instance_id: UUID) -> None:
        self._session.execute(
            update(timers_table)
            .where(
                and_(
                    timers_table.c.instance_id == instance_id,
                    timers_table.c.status == "pending",
                )
            )
            .values(status="cancelled")
        )
