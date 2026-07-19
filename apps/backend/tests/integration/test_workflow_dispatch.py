"""Dispatcher: idempotent inbox, persisted timer, bounded retry / crash recovery."""

from __future__ import annotations

import json
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.workflow_runtime.application.dto import ScheduleTimerCommand
from flowpilot.modules.workflow_runtime.application.service import WorkflowRuntimeService
from tests.integration.workflow_support import (
    AMOUNT_LOW,
    AMOUNT_MID,
    T0,
    decide,
    publish,
    scoped_count,
    start_and_submit,
)


def _set_tenant(session: Session, tenant_id: UUID) -> None:
    session.execute(
        text("SELECT set_config('app.current_tenant_id', :v, true)"), {"v": str(tenant_id)}
    )


def test_duplicate_event_produces_no_second_side_effect(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    v1, _ = publish(runtime_service, tenant_a)
    flow = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v1, AMOUNT_LOW)
    decide(runtime_service, flow, 0)

    stats = runtime_service.run_dispatch_pass(tenant_id=tenant_a, worker_id="w1")
    assert stats.processed >= 1
    assert (
        scoped_count(
            app_sessionmaker,
            tenant_a,
            "workflow_runtime_events",
            instance_id=str(flow.instance_id),
            event_type="notification.dispatched",
        )
        == 1
    )

    # Yeniden teslim simülasyonu: notification event'ini tekrar 'pending' yap
    # (crash sonrası re-delivery); inbox kaydı DURUYOR.
    with app_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant_a)
        s.execute(
            text(
                "UPDATE workflow_runtime_outbox SET status = 'pending', processed_at = NULL, "
                "claimed_by = NULL, claim_expires_at = NULL "
                "WHERE event_type = 'notification.requested.v1'"
            )
        )
    stats2 = runtime_service.run_dispatch_pass(tenant_id=tenant_a, worker_id="w2")
    assert stats2.duplicate == 1
    assert stats2.processed == 0
    # İKİNCİ notification.dispatched OLUŞMAZ.
    assert (
        scoped_count(
            app_sessionmaker,
            tenant_a,
            "workflow_runtime_events",
            instance_id=str(flow.instance_id),
            event_type="notification.dispatched",
        )
        == 1
    )


def test_persisted_timer_fires_exactly_once(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    v1, _ = publish(runtime_service, tenant_a)
    flow = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v1, AMOUNT_MID)
    fire_at = T0 + timedelta(seconds=60)
    runtime_service.schedule_timer(
        ScheduleTimerCommand(
            tenant_id=tenant_a,
            instance_id=flow.instance_id,
            purpose="approval.reminder",
            fire_at=fire_at,
        )
    )
    # Vadesinden önce: ateşlenmez.
    early = runtime_service.run_dispatch_pass(tenant_id=tenant_a, worker_id="w", now=T0)
    assert early.fired_timers == 0

    # Vadesinden sonra: tam bir kez ateşler + bildirim üretir.
    after = T0 + timedelta(seconds=120)
    fired = runtime_service.run_dispatch_pass(tenant_id=tenant_a, worker_id="w", now=after)
    assert fired.fired_timers == 1
    # İkinci tur: ikinci ateşleme YOK.
    again = runtime_service.run_dispatch_pass(tenant_id=tenant_a, worker_id="w", now=after)
    assert again.fired_timers == 0
    assert scoped_count(app_sessionmaker, tenant_a, "workflow_runtime_timers", status="fired") == 1


def test_lease_recovery_after_worker_crash(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    """Crash eden worker'ın lease'i dolunca iş yeniden alınır; duplicate yok."""
    v1, _ = publish(runtime_service, tenant_a)
    flow = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v1, AMOUNT_LOW)
    decide(runtime_service, flow, 0)

    # 'dead-worker' event'i claim etti (lease geleceğe yazıldı) ve çöktü.
    # available_at da T0'a çekilir (servis SystemClock kullanır; test T0 ile sürer).
    with app_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant_a)
        s.execute(
            text(
                "UPDATE workflow_runtime_outbox "
                "SET claimed_by = 'dead-worker', claim_expires_at = :future, available_at = :t0 "
                "WHERE event_type = 'notification.requested.v1' AND status = 'pending'"
            ),
            {"future": T0 + timedelta(seconds=60), "t0": T0},
        )

    # Lease dolmadan: başka worker claim EDEMEZ.
    blocked = runtime_service.run_dispatch_pass(tenant_id=tenant_a, worker_id="w2", now=T0)
    assert blocked.processed == 0
    assert (
        scoped_count(
            app_sessionmaker,
            tenant_a,
            "workflow_runtime_events",
            event_type="notification.dispatched",
        )
        == 0
    )

    # Lease dolunca: iş yeniden alınır ve TAM BİR KEZ tamamlanır.
    recovered = runtime_service.run_dispatch_pass(
        tenant_id=tenant_a, worker_id="w3", now=T0 + timedelta(seconds=120)
    )
    assert recovered.processed == 1
    assert (
        scoped_count(
            app_sessionmaker,
            tenant_a,
            "workflow_runtime_events",
            instance_id=str(flow.instance_id),
            event_type="notification.dispatched",
        )
        == 1
    )


def test_bounded_retry_then_failed_with_incident(
    runtime_service: WorkflowRuntimeService,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    """Handler kalıcı hata verirse: bounded retry sonra 'failed' (sonsuz retry yok)."""
    v1, _ = publish(runtime_service, tenant_a)
    flow = start_and_submit(runtime_service, app_sessionmaker, tenant_a, v1, AMOUNT_LOW)

    # Bozuk bir notification event'i enqueue et (instance_id eksik → handler KeyError).
    with app_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant_a)
        s.execute(
            text(
                "INSERT INTO workflow_runtime_outbox "
                "(tenant_id, event_id, event_type, payload, available_at, created_at) "
                "VALUES (:t, :e, 'notification.requested.v1', :p, :now, :now)"
            ),
            {
                "t": str(tenant_a),
                "e": str(uuid4()),
                "p": json.dumps({"tenant_id": str(tenant_a)}),
                "now": T0,
            },
        )

    # Turları ilerleterek backoff'u tüket; MAX_ATTEMPTS=5 → 4 retry + 1 failed.
    total_retry = total_failed = 0
    for i in range(8):
        stats = runtime_service.run_dispatch_pass(
            tenant_id=tenant_a, worker_id="w", now=T0 + timedelta(seconds=30 * (i + 1))
        )
        total_retry += stats.retried
        total_failed += stats.failed
    assert total_retry == 4
    assert total_failed == 1

    with app_sessionmaker() as s, s.begin():
        _set_tenant(s, tenant_a)
        status, attempt = s.execute(
            text(
                "SELECT status, attempt FROM workflow_runtime_outbox "
                "WHERE payload->>'instance_id' IS NULL"
            )
        ).one()
    assert status == "failed"
    assert attempt == 5
    _ = flow
