"""SPK-05 — Duplicate approval: eşzamanlı/tekrarlı komut → TEK karar, TEK geçiş.

Koruma DB düzeyindedir: UNIQUE(step_id) + optimistic lock (version + status CAS).
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime import engine as rt
from spike_runtime.db import set_tenant_context
from spike_runtime.errors import DuplicateDecisionError, SpikeError, StaleVersionError

from .conftest import T0
from .flow_helpers import approve_step, publish_v1, scoped_count, start_and_submit


def _assert_single_decision_and_single_transition(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID, flow_instance: uuid.UUID
) -> None:
    assert scoped_count(app_sf, tenant_a, "spike_approval_decisions") == 1
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        statuses = dict(
            s.execute(
                text("SELECT step_index, status FROM spike_approval_steps WHERE instance_id = :i"),
                {"i": str(flow_instance)},
            ).all()
        )
        decided_events = s.execute(
            text(
                "SELECT count(*) FROM spike_outbox_events WHERE event_type = 'approval.decided.v1'"
            )
        ).scalar_one()
    assert statuses == {0: "approved", 1: "active"}, "workflow BİR kez ilerlemeli"
    assert decided_events == 1, "outbox'ta TEK approval.decided event'i olmalı"


def test_concurrent_same_actor_double_click(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID
) -> None:
    """Aynı actor + aynı idempotency key, PARALEL iki istek (çift tıklama)."""
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 3_000_000, T0)
    actor = uuid.uuid4()

    def attempt(_: int) -> rt.DecisionResult | Exception:
        try:
            return approve_step(app_sf, flow, 0, T0, actor=actor, idempotency_key="double-click")
        except SpikeError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))

    winners = [o for o in outcomes if isinstance(o, rt.DecisionResult) and not o.duplicate]
    others = [o for o in outcomes if o not in winners]
    assert len(winners) == 1, f"tam olarak bir istek kazanmalı: {outcomes}"
    # Kaybeden ya idempotent aynı sonucu alır ya kontrollü conflict — ASLA crash.
    for other in others:
        assert isinstance(other, rt.DecisionResult | StaleVersionError | DuplicateDecisionError)
        if isinstance(other, rt.DecisionResult):
            assert other.duplicate is True
            assert other.decision == "approved"
    _assert_single_decision_and_single_transition(app_sf, tenant_a, flow.instance_id)


def test_sequential_retry_is_idempotent(app_sf: sessionmaker[Session], tenant_a: uuid.UUID) -> None:
    """Aynı komut sıralı iki kez (retry): ikinci çağrı idempotent sonuç döner."""
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 3_000_000, T0)
    actor = uuid.uuid4()

    first = approve_step(app_sf, flow, 0, T0, actor=actor, idempotency_key="retry-1")
    second = approve_step(app_sf, flow, 0, T0, actor=actor, idempotency_key="retry-1")

    assert first.duplicate is False
    assert second.duplicate is True, "retry idempotent sonuç dönmeli, yeni karar DEĞİL"
    assert second.decision == first.decision
    _assert_single_decision_and_single_transition(app_sf, tenant_a, flow.instance_id)


def test_two_different_approvers_race(app_sf: sessionmaker[Session], tenant_a: uuid.UUID) -> None:
    """İki FARKLI onaycı aynı step'e eşzamanlı karar verir: biri kazanır,
    diğeri kontrollü conflict alır (idempotent replay DEĞİL — farklı actor)."""
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 3_000_000, T0)

    def attempt(i: int) -> rt.DecisionResult | Exception:
        try:
            return approve_step(
                app_sf, flow, 0, T0, actor=uuid.uuid4(), idempotency_key=f"actor-{i}"
            )
        except SpikeError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))

    winners = [o for o in outcomes if isinstance(o, rt.DecisionResult) and not o.duplicate]
    losers = [o for o in outcomes if o not in winners]
    assert len(winners) == 1
    assert len(losers) == 1
    assert isinstance(losers[0], StaleVersionError | DuplicateDecisionError), (
        f"kaybeden kontrollü conflict almalı: {losers[0]!r}"
    )
    _assert_single_decision_and_single_transition(app_sf, tenant_a, flow.instance_id)
