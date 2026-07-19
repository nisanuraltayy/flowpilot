"""Concurrency: duplicate approval, eşzamanlı submit, eşzamanlı claim → tek kazanan."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.workflow_runtime.application.dto import (
    DecisionResult,
    StartInstanceCommand,
    SubmitFormCommand,
)
from flowpilot.modules.workflow_runtime.application.service import WorkflowRuntimeService
from flowpilot.modules.workflow_runtime.domain.errors import (
    ConcurrencyConflictError,
    DuplicateDecisionError,
    InvalidTransitionError,
    WorkflowRuntimeError,
)
from tests.integration.workflow_support import (
    AMOUNT_LOW,
    AMOUNT_MID,
    decide,
    publish,
    scoped_count,
    start_and_submit,
    task_status_map,
)


def test_concurrent_duplicate_approval_single_winner(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    v1, _ = publish(runtime_service, tenant_a)
    flow = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v1, AMOUNT_MID)
    actor = uuid4()

    def attempt(_: int) -> object:
        try:
            return decide(runtime_service, flow, 0, actor=actor, idempotency_key="double-click")
        except WorkflowRuntimeError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))

    winners = [o for o in outcomes if isinstance(o, DecisionResult) and not o.duplicate]
    assert len(winners) == 1, f"tam olarak bir kazanan: {outcomes}"
    for other in outcomes:
        if other not in winners:
            assert isinstance(
                other, DecisionResult | ConcurrencyConflictError | DuplicateDecisionError
            )

    # Tek karar, tek geçiş, tek outbox event.
    assert (
        scoped_count(
            app_sessionmaker, tenant_a, "workflow_runtime_outbox", event_type="task.decided.v1"
        )
        == 1
    )
    assert task_status_map(app_sessionmaker, tenant_a, flow.instance_id) == {
        0: "approved",
        1: "active",
    }


def test_sequential_retry_is_idempotent(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    v1, _ = publish(runtime_service, tenant_a)
    flow = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v1, AMOUNT_MID)
    actor = uuid4()
    first = decide(runtime_service, flow, 0, actor=actor, idempotency_key="retry-1")
    second = decide(runtime_service, flow, 0, actor=actor, idempotency_key="retry-1")
    assert first.duplicate is False
    assert second.duplicate is True
    assert (
        scoped_count(
            app_sessionmaker, tenant_a, "workflow_runtime_outbox", event_type="task.decided.v1"
        )
        == 1
    )


def test_concurrent_form_submit_single_winner(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    v1, _ = publish(runtime_service, tenant_a)
    actor = uuid4()
    started = runtime_service.start_instance(
        StartInstanceCommand(
            tenant_id=tenant_a, actor_user_id=actor, definition_version_id=v1, request_id="r"
        )
    )

    def attempt(i: int) -> str:
        try:
            runtime_service.submit_form(
                SubmitFormCommand(
                    tenant_id=tenant_a,
                    actor_user_id=actor,
                    instance_id=started.instance_id,
                    expected_version=started.version,
                    form_data={"amount_minor": AMOUNT_MID, "currency": "TRY"},
                    request_id=f"r-{i}",
                )
            )
            return "ok"
        except (ConcurrencyConflictError, InvalidTransitionError):
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(attempt, range(2)))
    assert outcomes == ["conflict", "ok"]
    # Adımlar tek kez oluştu (mid bandı → 2 adım).
    assert scoped_count(app_sessionmaker, tenant_a, "workflow_runtime_tasks") == 2


def test_concurrent_dispatch_no_duplicate_side_effect(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    """İki eşzamanlı dispatch turu (SKIP LOCKED + inbox) → duplicate bildirim yok."""
    v1, _ = publish(runtime_service, tenant_a)
    instance_ids = []
    for _ in range(6):
        flow = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v1, AMOUNT_LOW)
        decide(runtime_service, flow, 0)  # tamamlanır → notification.requested üretir
        instance_ids.append(flow.instance_id)

    def worker(name: str) -> int:
        stats = runtime_service.run_dispatch_pass(tenant_id=tenant_a, worker_id=name, limit=50)
        return stats.processed

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, ["w1", "w2"]))

    # Her instance için TAM BİR notification.dispatched (duplicate yok).
    for instance_id in instance_ids:
        assert (
            scoped_count(
                app_sessionmaker,
                tenant_a,
                "workflow_runtime_events",
                instance_id=str(instance_id),
                event_type="notification.dispatched",
            )
            == 1
        )
    # Hiç pending outbox kalmadı.
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"), {"v": str(tenant_a)}
        )
        pending = s.execute(
            text("SELECT count(*) FROM workflow_runtime_outbox WHERE status = 'pending'")
        ).scalar_one()
    assert pending == 0
