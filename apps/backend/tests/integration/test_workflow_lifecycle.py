"""Lifecycle: immutability, version pinning, atomicity, terminal guard, reload."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.workflow_runtime.application.dto import (
    DecideTaskCommand,
    StartInstanceCommand,
    SubmitFormCommand,
)
from flowpilot.modules.workflow_runtime.application.service import WorkflowRuntimeService
from flowpilot.modules.workflow_runtime.domain.errors import (
    ConditionEvaluationError,
    TerminalInstanceError,
)
from tests.integration.workflow_support import (
    AMOUNT_LOW,
    AMOUNT_MID,
    approve_all,
    decide,
    instance_status,
    publish,
    scoped_count,
    start_and_submit,
    task_status_map,
)
from tests.unit.workflow_runtime.definitions import purchase_like_v2


def test_published_version_is_immutable(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    migrator_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    version_id, content_hash = publish(runtime_service, tenant_a)

    # app rolü UPDATE grant'ı yok → ham SQL bile reddedilir.
    with pytest.raises(ProgrammingError), app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"), {"v": str(tenant_a)}
        )
        s.execute(
            text(
                "UPDATE workflow_runtime_definition_versions SET content_hash = 'x' WHERE id = :i"
            ),
            {"i": str(version_id)},
        )
    # owner (migrator) bile UPDATE edemez → immutability trigger.
    # migrator da FORCE RLS'e tabi: satırı görebilmek için tenant context set edilir,
    # böylece UPDATE RLS'i geçip trigger'a ulaşır ve trigger onu da engeller.
    with pytest.raises(DBAPIError, match="immutable"), migrator_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"), {"v": str(tenant_a)}
        )
        s.execute(
            text("UPDATE workflow_runtime_definition_versions SET version_no = 9 WHERE id = :i"),
            {"i": str(version_id)},
        )
    # Hash değişmedi.
    assert (
        scoped_count(
            app_sessionmaker,
            tenant_a,
            "workflow_runtime_definition_versions",
            id=str(version_id),
            content_hash=content_hash,
        )
        == 1
    )


def test_instance_pinned_to_start_version(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    v1, _ = publish(runtime_service, tenant_a)
    flow = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v1, AMOUNT_MID)
    assert flow.task_roles == ["team_manager", "finance"]  # v1 semantiği

    # v2 yayınla (farklı key ile — aynı definition_key immutable version zinciri gerektirmez).
    v2, _ = publish(runtime_service, tenant_a, definition=purchase_like_v2(), key="v2-key")

    # Bekleyen instance v1 ile tamamlanır (2 adım); yeni instance v2 (farklı roller).
    decide(runtime_service, flow, 0)
    result = decide(runtime_service, flow, 1)
    assert result.instance_status == "completed"

    flow_v2 = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v2, AMOUNT_MID)
    assert flow_v2.task_roles == ["finance", "general_manager"]

    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"), {"v": str(tenant_a)}
        )
        refs = dict(
            s.execute(
                text("SELECT id::text, definition_version_id::text FROM workflow_runtime_instances")
            ).all()
        )
    assert refs[str(flow.instance_id)] == str(v1)
    assert refs[str(flow_v2.instance_id)] == str(v2)


def test_condition_error_rolls_back_whole_submit(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    v1, _ = publish(runtime_service, tenant_a)
    started = runtime_service.start_instance(
        StartInstanceCommand(
            tenant_id=tenant_a,
            actor_user_id=uuid4(),
            definition_version_id=v1,
            request_id="r",
        )
    )
    with pytest.raises(ConditionEvaluationError, match="para birimi"):
        runtime_service.submit_form(
            SubmitFormCommand(
                tenant_id=tenant_a,
                actor_user_id=uuid4(),
                instance_id=started.instance_id,
                expected_version=started.version,
                form_data={"amount_minor": 1_000_000, "currency": "USD"},
                request_id="r",
            )
        )
    # Rollback: task ve condition node event'i yok; instance form node'unda kaldı.
    assert scoped_count(app_sessionmaker, tenant_a, "workflow_runtime_tasks") == 0
    assert instance_status(app_sessionmaker, tenant_a, started.instance_id) == "waiting"


def test_full_flow_atomic_writes(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    v1, _ = publish(runtime_service, tenant_a)
    flow = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v1, AMOUNT_LOW)
    result = approve_all(runtime_service, flow)
    assert result.instance_status == "completed"
    # Karar + state + timeline + outbox aynı akışta yazıldı.
    assert (
        scoped_count(
            app_sessionmaker, tenant_a, "workflow_runtime_outbox", event_type="task.decided.v1"
        )
        == 1
    )
    assert (
        scoped_count(
            app_sessionmaker,
            tenant_a,
            "workflow_runtime_outbox",
            event_type="notification.requested.v1",
        )
        == 1
    )


def test_terminal_instance_rejects_late_decision(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    v1, _ = publish(runtime_service, tenant_a)
    flow = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v1, AMOUNT_LOW)
    approve_all(runtime_service, flow)
    events_before = scoped_count(
        app_sessionmaker, tenant_a, "workflow_runtime_events", instance_id=str(flow.instance_id)
    )
    with pytest.raises(TerminalInstanceError):
        runtime_service.decide_task(
            DecideTaskCommand(
                tenant_id=tenant_a,
                actor_user_id=uuid4(),
                task_id=flow.task_ids[0],
                approver_role="team_manager",
                decision="approved",
                idempotency_key="late",
                request_id="r",
            )
        )
    assert (
        scoped_count(
            app_sessionmaker,
            tenant_a,
            "workflow_runtime_events",
            instance_id=str(flow.instance_id),
        )
        == events_before
    )


def test_rejection_cancels_open_steps_and_terminates(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    v1, _ = publish(runtime_service, tenant_a)
    flow = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v1, AMOUNT_MID)
    result = decide(runtime_service, flow, 0, decision="rejected")
    assert result.instance_status == "rejected"
    statuses = set(task_status_map(app_sessionmaker, tenant_a, flow.instance_id).values())
    assert statuses == {"rejected", "cancelled"}


def test_deterministic_reload_completes(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    """Her komut ayrı session/transaction; state yalnız DB'den yeniden yüklenir."""
    v1, _ = publish(runtime_service, tenant_a)
    flow = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v1, AMOUNT_MID)
    decide(runtime_service, flow, 0)
    assert task_status_map(app_sessionmaker, tenant_a, flow.instance_id) == {
        0: "approved",
        1: "active",
    }
    result = decide(runtime_service, flow, 1)
    assert result.instance_status == "completed"

    view = runtime_service.load_instance(tenant_id=tenant_a, instance_id=flow.instance_id)
    assert view.status == "completed"
    assert view.current_node_id == "end"
