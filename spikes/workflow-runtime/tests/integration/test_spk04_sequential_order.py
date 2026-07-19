"""SPK-04 — Sıralı onayda ikinci adım, birinci tamamlanmadan aktif OLMAZ.

(a) erken karar reddedilir + karar kaydı oluşmaz + red audit'e yazılır,
(b) birinci onay ikinciyi aktifleştirir (süreç ASILI KALMAZ),
(c) ardından karar kabul edilir.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime.db import set_tenant_context
from spike_runtime.errors import SequenceOrderError, UnauthorizedApproverError

from .conftest import T0
from .flow_helpers import approve_step, publish_v1, scoped_count, start_and_submit


def test_sequence_cannot_be_skipped_and_does_not_hang(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 3_000_000, T0)  # 2 adım
    finance_actor = uuid.uuid4()

    # (a) Finans, birinci adım beklerken İKİNCİ adıma karar veremez.
    with pytest.raises(SequenceOrderError):
        approve_step(app_sf, flow, 1, T0, actor=finance_actor)

    def step_statuses() -> dict[int, str]:
        with app_sf() as s, s.begin():
            set_tenant_context(s, tenant_a)
            return dict(
                s.execute(
                    text(
                        "SELECT step_index, status FROM spike_approval_steps WHERE instance_id = :i"
                    ),
                    {"i": str(flow.instance_id)},
                ).all()
            )

    assert step_statuses() == {0: "active", 1: "pending"}, "step'ler değişmemeli"
    assert scoped_count(app_sf, tenant_a, "spike_approval_decisions") == 0, (
        "HİÇBİR karar kaydı oluşmamalı"
    )
    assert (
        scoped_count(app_sf, tenant_a, "spike_audit_events", action="approval.decision_denied") == 1
    ), "yetki reddi audit'e yazılmalı"

    # (a2) Rol uyuşmazlığı: finans rolü, AKTİF yönetici adımına da karar veremez.
    with pytest.raises(UnauthorizedApproverError):
        approve_step(
            app_sf,
            type(flow)(
                tenant_id=flow.tenant_id,
                version_id=flow.version_id,
                content_hash=flow.content_hash,
                instance_id=flow.instance_id,
                requester_id=flow.requester_id,
                step_ids=flow.step_ids,
                step_roles=["finance", "finance"],  # yanlış rol iddiası
            ),
            0,
            T0,
            actor=finance_actor,
        )
    assert scoped_count(app_sf, tenant_a, "spike_approval_decisions") == 0

    # (b) Yönetici onaylar → ikinci adım pending→active olur; instance waiting kalır.
    r1 = approve_step(app_sf, flow, 0, T0)
    assert r1.activated_step_index == 1
    assert r1.instance_status == "waiting"
    assert step_statuses() == {0: "approved", 1: "active"}, "süreç asılı kalmamalı"

    # (c) Şimdi finans kararı kabul edilir; instance ilerler.
    r2 = approve_step(app_sf, flow, 1, T0, actor=finance_actor)
    assert r2.instance_status == "completed"
    assert step_statuses() == {0: "approved", 1: "approved"}
