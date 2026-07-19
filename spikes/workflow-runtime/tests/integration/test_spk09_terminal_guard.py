"""SPK-09 — Terminal instance HİÇBİR yoldan (API, event, timer) ilerletilemez.

(a) gecikmeli komut (API yolu) reddedilir, (b) iptal edilmiş instance'ın açık
görünen adımına karar verilemez + cancel açık step/timer'ları kapatır,
(c) geciken timer tamamlanmış süreci diriltmez. Ek: tanımsız state geçişleri
kontrollü reddedilir (crash değil, tanımlı domain hatası).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime import engine as rt
from spike_runtime.db import set_actor_context, set_tenant_context
from spike_runtime.dispatcher import run_pass
from spike_runtime.errors import InvalidTransitionError, TerminalInstanceError

from .conftest import T0
from .flow_helpers import (
    approve_all,
    approve_step,
    publish_v1,
    scoped_count,
    start_and_submit,
)


def _node_exec_count(app_sf: sessionmaker[Session], tenant: uuid.UUID, instance: uuid.UUID) -> int:
    return scoped_count(app_sf, tenant, "spike_node_executions", instance_id=str(instance))


def test_a_completed_instance_rejects_late_command(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 500_000, T0)
    approve_all(app_sf, flow, T0)

    executions_before = _node_exec_count(app_sf, tenant_a, flow.instance_id)

    # Gecikmeli/tekrarlanan komut FARKLI actor'den gelir (idempotent replay değil).
    with pytest.raises(TerminalInstanceError):
        approve_step(app_sf, flow, 0, T0, actor=uuid.uuid4(), idempotency_key="late-cmd")

    assert _node_exec_count(app_sf, tenant_a, flow.instance_id) == executions_before, (
        "terminal instance'ta YENİ node execution oluşamaz"
    )
    assert (
        scoped_count(app_sf, tenant_a, "spike_audit_events", action="approval.decision_denied") >= 1
    )


def test_b_cancel_closes_open_work_and_blocks_decisions(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 3_000_000, T0)  # 2 adım, step0 aktif
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        rt.schedule_timer(
            s,
            tenant_id=tenant_a,
            instance_id=flow.instance_id,
            purpose="approval.reminder",
            fire_at=T0 + timedelta(seconds=30),
            now=T0,
        )

    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        set_actor_context(s, str(flow.requester_id))
        rt.cancel_instance(
            s,
            tenant_id=tenant_a,
            instance_id=flow.instance_id,
            actor_id=flow.requester_id,
            request_id="req-cancel",
            expected_version=2,  # start(1) + submit_form(+1)
            now=T0,
        )

    # Invariant §36.1/10: açık step ve timer'lar kapatıldı.
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        step_statuses = {
            str(r[0])
            for r in s.execute(
                text("SELECT DISTINCT status FROM spike_approval_steps WHERE instance_id = :i"),
                {"i": str(flow.instance_id)},
            ).all()
        }
        timer_statuses = {
            str(r[0])
            for r in s.execute(
                text("SELECT DISTINCT status FROM spike_timers WHERE instance_id = :i"),
                {"i": str(flow.instance_id)},
            ).all()
        }
    assert step_statuses == {"cancelled"}
    assert timer_statuses == {"cancelled"}

    # "Açık görünen" adıma karar denemesi → kontrollü red; karar kaydı YOK.
    with pytest.raises(TerminalInstanceError):
        approve_step(app_sf, flow, 0, T0)
    assert scoped_count(app_sf, tenant_a, "spike_approval_decisions") == 0

    # Terminal instance yeniden iptal/tamamlama komutu da alamaz.
    with pytest.raises(TerminalInstanceError), app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        rt.cancel_instance(
            s,
            tenant_id=tenant_a,
            instance_id=flow.instance_id,
            actor_id=flow.requester_id,
            request_id="req-cancel-2",
            expected_version=3,
            now=T0,
        )


def test_c_late_timer_cannot_resurrect_completed_instance(
    app_sf: sessionmaker[Session],
    worker_sf: sessionmaker[Session],
    admin_sf: sessionmaker[Session],
    tenant_a: uuid.UUID,
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 500_000, T0)
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        timer_id = rt.schedule_timer(
            s,
            tenant_id=tenant_a,
            instance_id=flow.instance_id,
            purpose="approval.reminder",
            fire_at=T0 + timedelta(seconds=30),
            now=T0,
        )
    approve_all(app_sf, flow, T0)  # tamamlanır → engine timer'ı iptal eder

    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        status = s.execute(
            text("SELECT status FROM spike_timers WHERE id = :id"), {"id": str(timer_id)}
        ).scalar_one()
    assert status == "cancelled", "terminal geçiş açık timer'ı iptal etmeli"

    # Tamamlanma akışının MEŞRU bildirim event'lerini önce boşalt; baseline'ı
    # ondan SONRA al ki timer'ın diriltme üretmediği net görülsün.
    run_pass(worker_sf, worker_id="drain-worker", now=T0)
    executions_before = _node_exec_count(app_sf, tenant_a, flow.instance_id)
    notifications_before = scoped_count(app_sf, tenant_a, "spike_notifications")

    # İkinci savunma: timer bir yarışla 'pending' kalmış OLSA BİLE dispatcher
    # terminal instance için ateşlemez (diriltme yok).
    with admin_sf() as s, s.begin():
        s.execute(
            text("UPDATE spike_timers SET status = 'pending' WHERE id = :id"),
            {"id": str(timer_id)},
        )

    stats = run_pass(worker_sf, worker_id="late-timer-worker", now=T0 + timedelta(seconds=120))
    assert stats["fired_timers"] == 0

    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        final = s.execute(
            text("SELECT status FROM spike_timers WHERE id = :id"), {"id": str(timer_id)}
        ).scalar_one()
    assert final == "cancelled"
    assert _node_exec_count(app_sf, tenant_a, flow.instance_id) == executions_before
    assert scoped_count(app_sf, tenant_a, "spike_notifications") == notifications_before


def test_invalid_transitions_are_controlled_domain_errors(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 500_000, T0)

    # Form zaten gönderildi — instance approval node'unda: ikinci submit reddedilir.
    with pytest.raises(InvalidTransitionError), app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        rt.submit_form(
            s,
            tenant_id=tenant_a,
            instance_id=flow.instance_id,
            form_data={"amount_minor": 500_000, "currency": "TRY"},
            actor_id=flow.requester_id,
            request_id="req",
            expected_version=2,
            now=T0,
        )

    # Tanımsız karar değeri kontrollü reddedilir.
    with pytest.raises(InvalidTransitionError):
        approve_step(app_sf, flow, 0, T0, decision="maybe")

    # Terminal instance'a form gönderimi de TerminalInstanceError'dur.
    approve_all(app_sf, flow, T0)
    with pytest.raises(TerminalInstanceError), app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        rt.submit_form(
            s,
            tenant_id=tenant_a,
            instance_id=flow.instance_id,
            form_data={"amount_minor": 500_000, "currency": "TRY"},
            actor_id=flow.requester_id,
            request_id="req",
            expected_version=3,
            now=T0,
        )
