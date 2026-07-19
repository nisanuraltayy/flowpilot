"""Cross-tenant izolasyon (RLS) — context yok/deny, cross-tenant görünmez, IDOR."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.workflow_runtime.application.dto import (
    CancelInstanceCommand,
    DecideTaskCommand,
)
from flowpilot.modules.workflow_runtime.application.service import WorkflowRuntimeService
from flowpilot.modules.workflow_runtime.domain.errors import (
    WorkflowInstanceNotFoundError,
    WorkflowTaskNotFoundError,
)
from tests.integration.workflow_support import (
    AMOUNT_MID,
    publish,
    scoped_count,
    start_and_submit,
)

RUNTIME_TABLES = (
    "workflow_runtime_instances",
    "workflow_runtime_tasks",
    "workflow_runtime_events",
    "workflow_runtime_definition_versions",
)


def test_no_context_returns_zero_rows(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_b: UUID,
) -> None:
    version_id, _ = publish(runtime_service, tenant_b)
    start_and_submit(runtime_service, app_sessionmaker, tenant_b, version_id, AMOUNT_MID)

    with app_sessionmaker() as session:
        for table in RUNTIME_TABLES:
            count = session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608
            assert count == 0, f"{table}: context'siz sorgu satır DÖNDÜREMEZ"


def test_tenant_a_cannot_see_tenant_b_rows(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
    tenant_b: UUID,
) -> None:
    vb, _ = publish(runtime_service, tenant_b)
    flow_b = start_and_submit(runtime_service, app_sessionmaker, tenant_b, vb, AMOUNT_MID)

    # Tenant A context'inde B'nin satırları hiç görünmez (filtresiz sorgu bile).
    with app_sessionmaker() as session, session.begin():
        session.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"), {"v": str(tenant_a)}
        )
        visible = session.execute(
            text("SELECT count(*) FROM workflow_runtime_instances")
        ).scalar_one()
    assert visible == 0
    assert (
        scoped_count(
            app_sessionmaker, tenant_b, "workflow_runtime_instances", id=str(flow_b.instance_id)
        )
        == 1
    )


def test_direct_uuid_guess_does_not_leak_existence(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
    tenant_b: UUID,
) -> None:
    vb, _ = publish(runtime_service, tenant_b)
    flow_b = start_and_submit(runtime_service, app_sessionmaker, tenant_b, vb, AMOUNT_MID)

    # Gerçek B UUID'si ile A'dan karar → NotFound (rastgele UUID ile aynı davranış).
    for target in (flow_b.task_ids[0], uuid4()):
        with pytest.raises(WorkflowTaskNotFoundError):
            runtime_service.decide_task(
                DecideTaskCommand(
                    tenant_id=tenant_a,
                    actor_user_id=uuid4(),
                    task_id=target,
                    approver_role="team_manager",
                    decision="approved",
                    idempotency_key=f"idor-{target}",
                    request_id="req",
                )
            )
    with pytest.raises(WorkflowInstanceNotFoundError):
        runtime_service.cancel_instance(
            CancelInstanceCommand(
                tenant_id=tenant_a,
                actor_user_id=uuid4(),
                instance_id=flow_b.instance_id,
                expected_version=1,
                request_id="req",
            )
        )

    # B'nin verisi B context'inde sağlam (yanlışlıkla mutasyon yok).
    assert (
        scoped_count(
            app_sessionmaker,
            tenant_b,
            "workflow_runtime_instances",
            id=str(flow_b.instance_id),
            status="waiting",
        )
        == 1
    )


def test_cross_tenant_write_rejected_by_rls_with_check(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
    tenant_b: UUID,
) -> None:
    vb, _ = publish(runtime_service, tenant_b)
    flow_b = start_and_submit(runtime_service, app_sessionmaker, tenant_b, vb, AMOUNT_MID)

    # A context'iyle B tenant_id'sine event INSERT → RLS WITH CHECK reddeder.
    with (
        pytest.raises(DBAPIError, match=r"row-level security|policy"),
        app_sessionmaker() as session,
        session.begin(),
    ):
        session.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"),
            {"v": str(tenant_a)},
        )
        session.execute(
            text(
                "INSERT INTO workflow_runtime_events "
                "(id, tenant_id, instance_id, event_type, actor_type, detail, occurred_at) "
                "VALUES (:id, :tb, :inst, 'forged', 'system', '{}'::jsonb, now())"
            ),
            {"id": str(uuid4()), "tb": str(tenant_b), "inst": str(flow_b.instance_id)},
        )
