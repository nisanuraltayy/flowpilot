"""Workflow runtime integration testleri için ortak yardımcılar (pytest toplamaz).

Servisi gerçek `flowpilot_app` (NOBYPASSRLS) sessionmaker'ı üzerinden kurar;
akışı public WorkflowRuntimePort sözleşmesi üzerinden sürer (adapter internals'a
kör). Assertion'lar RLS'e tabi app rolüyle, tenant context altında okur.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.workflow_runtime.application.dto import (
    DecideTaskCommand,
    PublishDefinitionCommand,
    StartInstanceCommand,
    SubmitFormCommand,
)
from flowpilot.modules.workflow_runtime.application.service import WorkflowRuntimeService
from flowpilot.modules.workflow_runtime.infrastructure.persistence.unit_of_work import (
    SqlAlchemyWorkflowUnitOfWork,
)
from flowpilot.shared.clock import SystemClock
from flowpilot.shared.ids import UuidGenerator
from tests.unit.workflow_runtime.definitions import purchase_like_v1

T0 = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
AMOUNT_LOW = 500_000  # 5.000 TL → tek adım
AMOUNT_MID = 3_000_000  # 30.000 TL → iki adım


def build_service(app_sessionmaker: sessionmaker[Session]) -> WorkflowRuntimeService:
    return WorkflowRuntimeService(
        unit_of_work_factory=lambda: SqlAlchemyWorkflowUnitOfWork(app_sessionmaker),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


@dataclass(frozen=True)
class Flow:
    tenant_id: UUID
    actor_id: UUID
    version_id: UUID
    content_hash: str
    instance_id: UUID
    instance_version: int
    task_ids: list[UUID]
    task_roles: list[str]


def publish(
    service: WorkflowRuntimeService,
    tenant_id: UUID,
    *,
    definition: dict[str, Any] | None = None,
    key: str = "test-purchase-like",
) -> tuple[UUID, str]:
    result = service.publish_definition(
        PublishDefinitionCommand(
            tenant_id=tenant_id,
            actor_user_id=uuid4(),
            definition_key=key,
            definition=definition or purchase_like_v1(),
            request_id="req-publish",
        )
    )
    return result.definition_version_id, result.content_hash


def start_and_submit(
    service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_id: UUID,
    version_id: UUID,
    amount_minor: int,
    *,
    currency: str = "TRY",
) -> Flow:
    actor = uuid4()
    started = service.start_instance(
        StartInstanceCommand(
            tenant_id=tenant_id,
            actor_user_id=actor,
            definition_version_id=version_id,
            request_id="req-start",
        )
    )
    submitted = service.submit_form(
        SubmitFormCommand(
            tenant_id=tenant_id,
            actor_user_id=actor,
            instance_id=started.instance_id,
            expected_version=started.version,
            form_data={"amount_minor": amount_minor, "currency": currency, "item": "x"},
            request_id="req-submit",
        )
    )
    task_ids, task_roles = _load_tasks(app_sessionmaker, tenant_id, started.instance_id)
    return Flow(
        tenant_id=tenant_id,
        actor_id=actor,
        version_id=version_id,
        content_hash=submitted.definition_hash,
        instance_id=started.instance_id,
        instance_version=submitted.version,
        task_ids=task_ids,
        task_roles=task_roles,
    )


def decide(
    service: WorkflowRuntimeService,
    flow: Flow,
    step_index: int,
    *,
    decision: str = "approved",
    actor: UUID | None = None,
    idempotency_key: str | None = None,
) -> Any:
    return service.decide_task(
        DecideTaskCommand(
            tenant_id=flow.tenant_id,
            actor_user_id=actor or uuid4(),
            task_id=flow.task_ids[step_index],
            approver_role=flow.task_roles[step_index],
            decision=decision,
            idempotency_key=idempotency_key or f"idem-{flow.instance_id}-{step_index}",
            request_id=f"req-decide-{step_index}",
        )
    )


def approve_all(service: WorkflowRuntimeService, flow: Flow) -> Any:
    result = None
    for index in range(len(flow.task_ids)):
        result = decide(service, flow, index)
    return result


def _load_tasks(
    app_sessionmaker: sessionmaker[Session], tenant_id: UUID, instance_id: UUID
) -> tuple[list[UUID], list[str]]:
    with app_sessionmaker() as session, session.begin():
        _set_tenant(session, tenant_id)
        rows = session.execute(
            text(
                "SELECT id, approver_role FROM workflow_runtime_tasks "
                "WHERE instance_id = :i ORDER BY step_index"
            ),
            {"i": str(instance_id)},
        ).all()
    return [r[0] for r in rows], [str(r[1]) for r in rows]


def _set_tenant(session: Session, tenant_id: UUID) -> None:
    session.execute(
        text("SELECT set_config('app.current_tenant_id', :v, true)"), {"v": str(tenant_id)}
    )


def scoped_count(
    app_sessionmaker: sessionmaker[Session], tenant_id: UUID, table: str, **where: str
) -> int:
    clause = " AND ".join(f"{k} = :{k}" for k in where) or "TRUE"
    with app_sessionmaker() as session, session.begin():
        _set_tenant(session, tenant_id)
        value = session.execute(
            text(f"SELECT count(*) FROM {table} WHERE {clause}"),  # noqa: S608 — test yardımcı
            dict(where.items()),
        ).scalar_one()
    return int(value)


def task_status_map(
    app_sessionmaker: sessionmaker[Session], tenant_id: UUID, instance_id: UUID
) -> dict[int, str]:
    with app_sessionmaker() as session, session.begin():
        _set_tenant(session, tenant_id)
        rows = session.execute(
            text("SELECT step_index, status FROM workflow_runtime_tasks WHERE instance_id = :i"),
            {"i": str(instance_id)},
        ).all()
    return {int(r[0]): str(r[1]) for r in rows}


def instance_status(
    app_sessionmaker: sessionmaker[Session], tenant_id: UUID, instance_id: UUID
) -> str:
    with app_sessionmaker() as session, session.begin():
        _set_tenant(session, tenant_id)
        return str(
            session.execute(
                text("SELECT status FROM workflow_runtime_instances WHERE id = :i"),
                {"i": str(instance_id)},
            ).scalar_one()
        )
