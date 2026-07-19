"""SPK-06 — Aynı outbox event'i iki kez işlenirse duplicate side effect OLUŞMAZ.

At-least-once teslim + idempotent inbox (spike_processed_events PK).
Ayrıca: iki worker aynı event'i aynı anda alamaz (FOR UPDATE SKIP LOCKED).
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime.dispatcher import claim_events, run_pass

from .conftest import T0
from .flow_helpers import approve_all, publish_v1, scoped_count, start_and_submit


def _complete_low_flow(app_sf: sessionmaker[Session], tenant: uuid.UUID) -> uuid.UUID:
    v1 = publish_v1(app_sf, tenant, T0)
    flow = start_and_submit(app_sf, tenant, v1.id, 500_000, T0)  # tek adım
    approve_all(app_sf, flow, T0)
    return flow.instance_id


def test_redelivered_event_produces_no_second_side_effect(
    app_sf: sessionmaker[Session],
    worker_sf: sessionmaker[Session],
    admin_sf: sessionmaker[Session],
    tenant_a: uuid.UUID,
) -> None:
    instance_id = _complete_low_flow(app_sf, tenant_a)

    stats = run_pass(worker_sf, worker_id="w1", now=T0)
    assert stats["processed"] >= 1
    assert scoped_count(app_sf, tenant_a, "spike_notifications", instance_id=str(instance_id)) == 1

    def snapshot() -> tuple[int, int, int]:
        return (
            scoped_count(app_sf, tenant_a, "spike_notifications"),
            scoped_count(app_sf, tenant_a, "spike_audit_events"),
            scoped_count(app_sf, tenant_a, "spike_node_executions"),
        )

    before = snapshot()

    # Yeniden teslim simülasyonu: crash sonrası aynı event tekrar 'pending' olur
    # (dispatch işareti kayboldu ama inbox kaydı DURUYOR).
    with admin_sf() as s, s.begin():
        s.execute(
            text(
                "UPDATE spike_outbox_events SET status = 'pending', processed_at = NULL, "
                "claimed_by = NULL, claim_expires_at = NULL "
                "WHERE event_type = 'notification.requested.v1'"
            )
        )

    stats2 = run_pass(worker_sf, worker_id="w2", now=T0)
    assert stats2["duplicate"] == 1, "ikinci işleme inbox tarafından yakalanmalı"
    assert stats2["processed"] == 0

    assert snapshot() == before, "İKİNCİ side effect OLUŞMAMALI (bildirim/audit/node)"
    with worker_sf() as s, s.begin():
        inbox = s.execute(text("SELECT count(*) FROM spike_processed_events")).scalar_one()
        pending = s.execute(
            text("SELECT count(*) FROM spike_outbox_events WHERE status = 'pending'")
        ).scalar_one()
    assert pending == 0, "event yeniden 'processed' işaretlenmeli"
    assert inbox >= 1


def test_two_workers_cannot_claim_same_event(
    app_sf: sessionmaker[Session],
    worker_sf: sessionmaker[Session],
    tenant_a: uuid.UUID,
) -> None:
    _complete_low_flow(app_sf, tenant_a)

    with worker_sf() as s1, worker_sf() as s2, s1.begin():
        first = claim_events(s1, worker_id="w1", now=T0, limit=100)
        assert len(first) >= 1
        # s1 henüz COMMIT ETMEDİ — satırlar kilitli.
        with s2.begin():
            second = claim_events(s2, worker_id="w2", now=T0, limit=100)
            assert second == [], "SKIP LOCKED: ikinci worker aynı işi ALAMAZ"
