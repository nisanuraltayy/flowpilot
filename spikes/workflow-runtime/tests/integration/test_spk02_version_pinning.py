"""SPK-02 — Instance, BAŞLADIĞI version'a sabitlenir; yeni yayından etkilenmez.

Ayrıca deterministik devam (yeniden yükleme) kanıtı: her komut ayrı session ve
ayrı transaction'da çalışır — state tamamen veritabanından yeniden yüklenir.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime import engine as rt
from spike_runtime.db import set_actor_context, set_tenant_context
from spike_runtime.definition import load_fixture

from .conftest import T0
from .flow_helpers import approve_step, publish_v1, start_and_submit

AMOUNT_30K_TL = 3_000_000  # 30.000 TL (kuruş)


def test_pending_instance_completes_with_v1_semantics(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)

    # v1 semantiği: 30.000 TL → mid bandı → [team_manager, finance]
    flow = start_and_submit(app_sf, tenant_a, v1.id, AMOUNT_30K_TL, T0)
    assert flow.step_roles == ["team_manager", "finance"]

    # Instance onayda BEKLERKEN v2 yayınlanır (eşik 20.000; zincirler farklı).
    actor = uuid.uuid4()
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        set_actor_context(s, str(actor))
        v2 = rt.publish_version(
            s,
            tenant_id=tenant_a,
            workflow_key="purchase-request",
            version_no=2,
            definition=load_fixture("purchase_request_v2.json"),
            actor_id=actor,
            request_id="req-v2",
            now=T0,
        )

    # Bekleyen instance v1 KURALLARIYLA tamamlanır: hâlâ 2 adım, v1 rolleri.
    r1 = approve_step(app_sf, flow, 0, T0)
    assert r1.activated_step_index == 1, "birinci onaydan sonra ikinci adım aktifleşmeli"
    r2 = approve_step(app_sf, flow, 1, T0)
    assert r2.instance_status == "completed"

    # Yeni instance v2 ile başlar: 30.000 TL artık 'high' → [finance, general_manager].
    flow_v2 = start_and_submit(app_sf, tenant_a, v2.id, AMOUNT_30K_TL, T0)
    assert flow_v2.step_roles == ["finance", "general_manager"], (
        "yeni instance v2 semantiği kullanmalı"
    )

    # Her instance kaydı bağlı olduğu workflow_version_id'yi taşır — dinamik
    # 'son version' çözümü YOK.
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        refs = dict(
            s.execute(text("SELECT id::text, workflow_version_id::text FROM spike_instances")).all()
        )
    assert refs[str(flow.instance_id)] == str(v1.id)
    assert refs[str(flow_v2.instance_id)] == str(v2.id)


def test_state_reload_is_deterministic(app_sf: sessionmaker[Session], tenant_a: uuid.UUID) -> None:
    """Yarıda kalan instance, yalnız DB state'inden deterministik devam eder."""
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, AMOUNT_30K_TL, T0)
    approve_step(app_sf, flow, 0, T0)

    # "Yeniden yükleme": tüm önceki session'lar kapandı; yeni session'larla durum
    # okunur ve süreç kaldığı yerden tamamlanır.
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        statuses = dict(
            s.execute(
                text("SELECT step_index, status FROM spike_approval_steps WHERE instance_id = :i"),
                {"i": str(flow.instance_id)},
            ).all()
        )
    assert statuses == {0: "approved", 1: "active"}

    result = approve_step(app_sf, flow, 1, T0)
    assert result.instance_status == "completed"

    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        final = s.execute(
            text("SELECT status, current_node_id FROM spike_instances WHERE id = :i"),
            {"i": str(flow.instance_id)},
        ).one()
    assert (final[0], final[1]) == ("completed", "end")
