"""SPK-11 — State + outbox + audit: ya HEPSİ yazılır ya HİÇBİRİ.

Fault injection: commit'ten hemen önce yapay hata → dört tablo da değişmemiş
olmalı. Ardından aynı işlem tekrar denenir → üçü birlikte yazılır. Side effect
başarısızlığı state'i GERİ ALMAZ; bounded retry + incident üretir.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime import engine as rt
from spike_runtime.db import set_actor_context, set_tenant_context
from spike_runtime.dispatcher import MAX_ATTEMPTS, ClaimedEvent, run_pass

from .conftest import T0
from .flow_helpers import approve_all, publish_v1, scoped_count, start_and_submit


class InjectedFault(RuntimeError):
    """Test amaçlı yapay hata."""


@dataclass(frozen=True)
class Snapshot:
    decisions: int
    outbox: int
    audit: int
    step_status: str
    step_version: int
    instance_status: str
    instance_version: int


def _snapshot(
    app_sf: sessionmaker[Session], tenant: uuid.UUID, instance: uuid.UUID, step: uuid.UUID
) -> Snapshot:
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant)
        step_row = s.execute(
            text("SELECT status, version FROM spike_approval_steps WHERE id = :s"),
            {"s": str(step)},
        ).one()
        inst_row = s.execute(
            text("SELECT status, version FROM spike_instances WHERE id = :i"),
            {"i": str(instance)},
        ).one()
        return Snapshot(
            decisions=int(
                s.execute(text("SELECT count(*) FROM spike_approval_decisions")).scalar_one()
            ),
            outbox=int(s.execute(text("SELECT count(*) FROM spike_outbox_events")).scalar_one()),
            audit=int(s.execute(text("SELECT count(*) FROM spike_audit_events")).scalar_one()),
            step_status=str(step_row[0]),
            step_version=int(step_row[1]),
            instance_status=str(inst_row[0]),
            instance_version=int(inst_row[1]),
        )


def test_fault_before_commit_rolls_back_everything(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 3_000_000, T0)
    actor = uuid.uuid4()
    before = _snapshot(app_sf, tenant_a, flow.instance_id, flow.step_ids[0])

    # Karar işlenir, TÜM yazımlar yapılır… ve commit'ten hemen önce hata patlar.
    with pytest.raises(InjectedFault), app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        set_actor_context(s, str(actor))
        result = rt.decide_step(
            s,
            tenant_id=tenant_a,
            step_id=flow.step_ids[0],
            actor_id=actor,
            approver_role="team_manager",
            decision="approved",
            idempotency_key="fault-1",
            request_id="req-fault",
            now=T0,
        )
        assert result.duplicate is False  # yazımlar transaction İÇİNDE başarılı
        raise InjectedFault("commit öncesi yapay hata")

    after_fault = _snapshot(app_sf, tenant_a, flow.instance_id, flow.step_ids[0])
    assert after_fault == before, (
        "KISMİ DURUM YASAK: karar/outbox/audit/step/instance hiçbiri değişmemeli"
    )

    # Hata kaldırılınca aynı işlem: ÜÇÜ BİRLİKTE yazılır.
    rt.decide_step_command(
        app_sf,
        tenant_id=tenant_a,
        step_id=flow.step_ids[0],
        actor_id=actor,
        approver_role="team_manager",
        decision="approved",
        idempotency_key="fault-1",
        request_id="req-retry",
        now=T0,
    )
    after_retry = _snapshot(app_sf, tenant_a, flow.instance_id, flow.step_ids[0])
    assert after_retry.decisions == before.decisions + 1
    assert after_retry.outbox == before.outbox + 1  # approval.decided.v1
    assert after_retry.audit == before.audit + 1  # approval.decided
    assert after_retry.step_status == "approved"


def test_side_effect_failure_keeps_state_and_produces_bounded_retry_incident(
    app_sf: sessionmaker[Session],
    worker_sf: sessionmaker[Session],
    tenant_a: uuid.UUID,
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 500_000, T0)
    approve_all(app_sf, flow, T0)  # instance completed; notification event kuyruğa girdi

    def fail_only_notification(event: ClaimedEvent) -> None:
        # Yalnız gerçek side effect'i olan notification event'ini düşür; diğer
        # event tipleri (started/form_submitted/decided) normal işlenir.
        if event.event_type == "notification.requested.v1":
            raise RuntimeError("bildirim kanalı çöktü (simülasyon)")

    total = {"failed": 0, "retry": 0}
    # Backoff'u beklemeden tüketmek için 'now'u her turda ileriye taşı.
    from datetime import timedelta

    for attempt in range(MAX_ATTEMPTS + 2):  # üst sınırı da kanıtla: fazladan tur boş döner
        stats = run_pass(
            worker_sf,
            worker_id="failing-worker",
            now=T0 + timedelta(seconds=30 * (attempt + 1)),
            fail_handler=fail_only_notification,
        )
        total["failed"] += stats["failed"]
        total["retry"] += stats["retry"]

    assert total["retry"] == MAX_ATTEMPTS - 1, "bounded retry: MAX_ATTEMPTS-1 yeniden deneme"
    assert total["failed"] == 1, "limitte TAM BİR kez 'failed' (sonsuz retry YOK)"

    with worker_sf() as s, s.begin():
        status, attempts = s.execute(
            text(
                "SELECT status, attempt FROM spike_outbox_events "
                "WHERE event_type = 'notification.requested.v1'"
            )
        ).one()
    assert status == "failed"
    assert attempts == MAX_ATTEMPTS

    # State GERİ ALINMADI (kullanıcının gördüğü onay sonucu geçerli kalır)…
    assert (
        scoped_count(
            app_sf, tenant_a, "spike_instances", id=str(flow.instance_id), status="completed"
        )
        == 1
    )
    # …ve başarısızlık kullanıcıdan GİZLENMEZ: audit'te incident kaydı var.
    assert scoped_count(app_sf, tenant_a, "spike_audit_events", action="outbox.event_failed") == 1
    # Side effect hiç üretilmedi (yarım bildirim yok).
    assert scoped_count(app_sf, tenant_a, "spike_notifications") == 0
