"""SPK-12 — Optimistic concurrency: conflict KONTROLLÜ hata üretir.

"Son yazan kazanır" YOK; sessiz veri kaybı YOK; deadlock YOK; retry bounded.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime import engine as rt
from spike_runtime.db import set_actor_context, set_tenant_context
from spike_runtime.errors import InvalidTransitionError, SpikeError, StaleVersionError

from .conftest import T0
from .flow_helpers import publish_v1, scoped_count, start_and_submit


def test_stale_step_version_gets_controlled_conflict(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID
) -> None:
    """İki actor aynı 'version' değerini okudu; ikincisi bayat yazma yapar."""
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 3_000_000, T0)

    winner = rt.decide_step_command(
        app_sf,
        tenant_id=tenant_a,
        step_id=flow.step_ids[0],
        actor_id=uuid.uuid4(),
        approver_role="team_manager",
        decision="approved",
        idempotency_key="winner",
        request_id="req-1",
        now=T0,
        expected_step_version=1,  # okuduğu değer
    )
    assert winner.duplicate is False

    # İkinci actor HÂLÂ version=1 gördüğünü sanıyor → step artık terminal;
    # farklı actor'ün komutu kontrollü DuplicateDecision/conflict üretir,
    # winner'ın kararı DEĞİŞMEZ (veri kaybı yok).
    from spike_runtime.errors import DuplicateDecisionError

    with pytest.raises((DuplicateDecisionError, StaleVersionError)):
        rt.decide_step_command(
            app_sf,
            tenant_id=tenant_a,
            step_id=flow.step_ids[0],
            actor_id=uuid.uuid4(),
            approver_role="team_manager",
            decision="rejected",  # kaybeden TERS karar deniyor — sessizce ezemez
            idempotency_key="loser",
            request_id="req-2",
            now=T0,
            expected_step_version=1,
        )

    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        decision = s.execute(
            text("SELECT decision FROM spike_approval_decisions WHERE step_id = :s"),
            {"s": str(flow.step_ids[0])},
        ).scalar_one()
    assert decision == "approved", "kazananın verisi KAYBOLMAMALI"


def test_stale_instance_version_on_submit_form(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)
    requester = uuid.uuid4()
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        set_actor_context(s, str(requester))
        instance = rt.start_instance(
            s,
            tenant_id=tenant_a,
            workflow_version_id=v1.id,
            requester_id=requester,
            request_id="req",
            now=T0,
        )

    with pytest.raises(StaleVersionError), app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        rt.submit_form(
            s,
            tenant_id=tenant_a,
            instance_id=instance.id,
            form_data={"amount_minor": 500_000, "currency": "TRY"},
            actor_id=requester,
            request_id="req",
            expected_version=99,  # bayat/yanlış version
            now=T0,
        )
    # Rollback: adım oluşmadı, instance form node'unda kaldı.
    assert scoped_count(app_sf, tenant_a, "spike_approval_steps") == 0
    assert (
        scoped_count(app_sf, tenant_a, "spike_instances", id=str(instance.id), status="waiting")
        == 1
    )


def test_concurrent_form_submit_race_single_winner_no_deadlock(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID
) -> None:
    """İki 'worker' aynı instance'ı aynı anda ilerletmeye çalışır (aynı version)."""
    v1 = publish_v1(app_sf, tenant_a, T0)
    requester = uuid.uuid4()
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        set_actor_context(s, str(requester))
        instance = rt.start_instance(
            s,
            tenant_id=tenant_a,
            workflow_version_id=v1.id,
            requester_id=requester,
            request_id="req",
            now=T0,
        )

    def attempt(i: int) -> str:
        try:
            with app_sf() as s, s.begin():
                set_tenant_context(s, tenant_a)
                set_actor_context(s, str(requester))
                rt.submit_form(
                    s,
                    tenant_id=tenant_a,
                    instance_id=instance.id,
                    form_data={"amount_minor": 3_000_000, "currency": "TRY"},
                    actor_id=requester,
                    request_id=f"req-{i}",
                    expected_version=instance.version,  # ikisi de aynı sürümü okudu
                    now=T0,
                )
            return "ok"
        except (StaleVersionError, InvalidTransitionError):
            # İki kontrollü conflict yolu (timing'e bağlı, ikisi de veri kaybı YOK):
            #  - kaybeden version CAS'ı kaybeder → StaleVersionError
            #  - ya da kazanan commit ettikten SONRA okur, node artık 'form' değil
            #    → InvalidTransitionError. Sessiz overwrite ASLA olmaz.
            return "conflict"
        except SpikeError as exc:  # beklenmeyen başka domain hatası → testi bozar
            return type(exc).__name__

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(attempt, range(2)))

    assert outcomes == ["conflict", "ok"], f"tek kazanan + kontrollü conflict: {outcomes}"
    # Adımlar YALNIZ bir kez oluştu; instance state bozulmadı.
    assert scoped_count(app_sf, tenant_a, "spike_approval_steps") == 2  # mid bandı zinciri
    assert (
        scoped_count(app_sf, tenant_a, "spike_instances", id=str(instance.id), status="waiting")
        == 1
    )


def test_all_mutable_aggregates_carry_version_column(
    admin_sf: sessionmaker[Session],
) -> None:
    """FF-05 analog: mutasyona açık spike aggregate'lerinde version alanı var."""
    with admin_sf() as s, s.begin():
        rows = s.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE column_name = 'version' AND table_name LIKE 'spike_%'"
            )
        ).all()
    tables = {str(r[0]) for r in rows}
    assert {"spike_instances", "spike_approval_steps"} <= tables
