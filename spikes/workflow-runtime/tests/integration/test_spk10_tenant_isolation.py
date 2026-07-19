"""SPK-10 — Cross-tenant erişim İKİ bağımsız katmanla engellenir.

Katman 1: uygulama tenant context'i (set_config). Katman 2: PostgreSQL RLS
(ENABLE + FORCE). Kanıtlar: context'siz erişim boş döner; Tenant A, B'nin
instance/step/timeline/notification kayıtlarına TAM UUID ile bile erişemez;
varlık bilgisi sızmaz; deneme audit'e yazılır; roller BYPASSRLS'sizdir.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime import engine as rt
from spike_runtime.db import set_tenant_context
from spike_runtime.errors import NotFoundError

from .conftest import T0
from .flow_helpers import FlowSetup, approve_step, publish_v1, scoped_count, start_and_submit


@pytest.fixture
def tenant_b_flow(app_sf: sessionmaker[Session], tenant_b: uuid.UUID) -> FlowSetup:
    v1 = publish_v1(app_sf, tenant_b, T0)
    return start_and_submit(app_sf, tenant_b, v1.id, 3_000_000, T0)


def test_no_context_means_zero_rows(
    app_sf: sessionmaker[Session], tenant_b_flow: FlowSetup
) -> None:
    """Tenant context YOKSA erişim varsayılan olarak REDDEDİLİR (0 satır)."""
    with app_sf() as s, s.begin():
        for table in ("spike_instances", "spike_approval_steps", "spike_audit_events"):
            count = s.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608
            assert count == 0, f"{table}: context'siz sorgu satır DÖNDÜREMEZ"


def test_rls_alone_blocks_filterless_query(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID, tenant_b_flow: FlowSetup
) -> None:
    """Uygulama WHERE filtresi BİLEREK YOK — yalnız RLS ikinci katmanı çalışıyor."""
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow_a = start_and_submit(app_sf, tenant_a, v1.id, 500_000, T0)

    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        rows = s.execute(text("SELECT id::text, tenant_id::text FROM spike_instances")).all()
    assert {r[0] for r in rows} == {str(flow_a.instance_id)}, (
        "filtresiz sorguda YALNIZ kendi tenant'ının satırları görünmeli"
    )
    assert all(r[1] == str(tenant_a) for r in rows)


def test_direct_uuid_guess_does_not_leak_existence(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID, tenant_b_flow: FlowSetup
) -> None:
    """Tenant A, B'nin GERÇEK UUID'leriyle bile: okuma boş, komutlar NotFound.

    Var olmayan UUID ile aynı davranış — kaynak VARLIĞI SIZDIRILMAZ.
    """
    publish_v1(app_sf, tenant_a, T0)
    actor_a = uuid.uuid4()

    # (a) okuma
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        row = s.execute(
            text("SELECT 1 FROM spike_instances WHERE id = :i"),
            {"i": str(tenant_b_flow.instance_id)},
        ).first()
    assert row is None

    # (b) iptal ve (c) approval kararı: gerçek B UUID'si ve rastgele UUID
    # AYNI hatayı üretir (NotFoundError) — 404/403 ayrımı bilgi sızdırmaz.
    for target_step in (tenant_b_flow.step_ids[0], uuid.uuid4()):
        with pytest.raises(NotFoundError):
            rt.decide_step_command(
                app_sf,
                tenant_id=tenant_a,
                step_id=target_step,
                actor_id=actor_a,
                approver_role="team_manager",
                decision="approved",
                idempotency_key=f"idor-{target_step}",
                request_id="req-idor",
                now=T0,
            )
    with pytest.raises(NotFoundError), app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        rt.cancel_instance(
            s,
            tenant_id=tenant_a,
            instance_id=tenant_b_flow.instance_id,
            actor_id=actor_a,
            request_id="req-idor-cancel",
            expected_version=1,
            now=T0,
        )

    # (d) timeline/audit ve (e) notification okuma — B'ye ait hiçbir satır yok.
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        for table in ("spike_node_executions", "spike_audit_events", "spike_notifications"):
            leaked = s.execute(
                text(f"SELECT count(*) FROM {table} WHERE tenant_id = :b"),  # noqa: S608
                {"b": str(tenant_b_flow.tenant_id)},
            ).scalar_one()
            assert leaked == 0, f"{table}: cross-tenant satır sızdı"

    # Denemeler Tenant A'nın güvenlik log'una yazıldı (kendi audit scope'unda).
    assert (
        scoped_count(app_sf, tenant_a, "spike_audit_events", action="approval.decision_denied") == 2
    )

    # B'nin verisi B context'inde SAĞLAM duruyor (yanlışlıkla mutasyon yok).
    assert (
        scoped_count(
            app_sf,
            tenant_b_flow.tenant_id,
            "spike_instances",
            id=str(tenant_b_flow.instance_id),
            status="waiting",
        )
        == 1
    )


def test_cross_tenant_write_is_rejected_by_rls_with_check(
    app_sf: sessionmaker[Session], tenant_a: uuid.UUID, tenant_b_flow: FlowSetup
) -> None:
    """A context'iyle B tenant_id'sine INSERT — RLS WITH CHECK reddeder."""
    with pytest.raises(DBAPIError, match=r"row-level security|policy"), app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        s.execute(
            text(
                "INSERT INTO spike_notifications "
                "(id, tenant_id, instance_id, recipient_role, message_key, "
                " source_event_id, created_at) "
                "VALUES (:id, :tenant_b, :instance, 'requester', 'forged', :src, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "tenant_b": str(tenant_b_flow.tenant_id),
                "instance": str(tenant_b_flow.instance_id),
                "src": str(uuid.uuid4()),
                "now": T0,
            },
        )


def test_worker_role_is_tenant_scoped_on_business_tables(
    worker_sf: sessionmaker[Session], app_sf: sessionmaker[Session], tenant_b_flow: FlowSetup
) -> None:
    """Worker kuyruk tablolarını yönetir ama business verisinde tenant-scoped'tur."""
    other_tenant = uuid.uuid4()
    with worker_sf() as s, s.begin():
        # Kuyruk tablosu: tasarım gereği görülür (dispatcher policy).
        outbox = s.execute(text("SELECT count(*) FROM spike_outbox_events")).scalar_one()
        assert outbox >= 1
        # Business tablosu: context'siz → 0 satır.
        assert s.execute(text("SELECT count(*) FROM spike_instances")).scalar_one() == 0
        # Yanlış tenant context'i → yine 0 satır.
        set_tenant_context(s, other_tenant)
        assert s.execute(text("SELECT count(*) FROM spike_instances")).scalar_one() == 0
        # Doğru context'te yalnız o tenant'ın satırı.
        set_tenant_context(s, tenant_b_flow.tenant_id)
        assert s.execute(text("SELECT count(*) FROM spike_instances")).scalar_one() == 1


def test_roles_have_no_bypassrls_or_superuser(admin_sf: sessionmaker[Session]) -> None:
    """En sinsi sızıntı yolu: worker'ın BYPASSRLS rolü — burada YOK."""
    with admin_sf() as s, s.begin():
        rows = s.execute(
            text(
                "SELECT rolname, rolbypassrls, rolsuper FROM pg_roles "
                "WHERE rolname IN ('spike_app','spike_worker')"
            )
        ).all()
    assert len(rows) == 2
    for name, bypass, superuser in rows:
        assert bypass is False, f"{name} BYPASSRLS taşıyamaz"
        assert superuser is False, f"{name} superuser olamaz"


def test_full_decision_flow_stays_isolated(
    app_sf: sessionmaker[Session],
    tenant_a: uuid.UUID,
    tenant_b_flow: FlowSetup,
) -> None:
    """A kendi akışını tamamlarken B'nin verisi değişmez (yan etki taşmaz)."""
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow_a = start_and_submit(app_sf, tenant_a, v1.id, 500_000, T0)
    approve_step(app_sf, flow_a, 0, T0)

    assert (
        scoped_count(
            app_sf,
            tenant_b_flow.tenant_id,
            "spike_approval_steps",
            instance_id=str(tenant_b_flow.instance_id),
            status="active",
        )
        == 1
    ), "B'nin aktif adımı A'nın işleminden etkilenmemeli"
    assert scoped_count(app_sf, tenant_b_flow.tenant_id, "spike_approval_decisions") == 0
