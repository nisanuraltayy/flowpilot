"""Testler için ortak akış yardımcıları (satın alma referans akışı)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime import engine as rt
from spike_runtime.db import set_actor_context, set_tenant_context
from spike_runtime.definition import load_fixture


@dataclass(frozen=True)
class FlowSetup:
    tenant_id: uuid.UUID
    version_id: uuid.UUID
    content_hash: str
    instance_id: uuid.UUID
    requester_id: uuid.UUID
    step_ids: list[uuid.UUID]
    step_roles: list[str]


def publish_v1(
    app_sf: sessionmaker[Session], tenant_id: uuid.UUID, now: datetime
) -> rt.PublishedVersion:
    actor = uuid.uuid4()
    with app_sf() as session, session.begin():
        set_tenant_context(session, tenant_id)
        set_actor_context(session, str(actor))
        return rt.publish_version(
            session,
            tenant_id=tenant_id,
            workflow_key="purchase-request",
            version_no=1,
            definition=load_fixture("purchase_request_v1.json"),
            actor_id=actor,
            request_id="req-publish-v1",
            now=now,
        )


def start_and_submit(
    app_sf: sessionmaker[Session],
    tenant_id: uuid.UUID,
    version_id: uuid.UUID,
    amount_minor: int,
    now: datetime,
    *,
    currency: str = "TRY",
    extra_form: dict[str, Any] | None = None,
) -> FlowSetup:
    """Instance başlatır, formu gönderir; aktifleşen onay zincirini döndürür."""
    requester = uuid.uuid4()
    with app_sf() as session, session.begin():
        set_tenant_context(session, tenant_id)
        set_actor_context(session, str(requester))
        instance = rt.start_instance(
            session,
            tenant_id=tenant_id,
            workflow_version_id=version_id,
            requester_id=requester,
            request_id="req-start",
            now=now,
        )
    with app_sf() as session, session.begin():
        set_tenant_context(session, tenant_id)
        set_actor_context(session, str(requester))
        rt.submit_form(
            session,
            tenant_id=tenant_id,
            instance_id=instance.id,
            form_data={
                "item_name": "Dizüstü bilgisayar",
                "category": "donanım",
                "amount_minor": amount_minor,
                "currency": currency,
                "justification": "spike kabul testi",
                **(extra_form or {}),
            },
            actor_id=requester,
            request_id="req-submit",
            expected_version=instance.version,
            now=now,
        )
    with app_sf() as session, session.begin():
        set_tenant_context(session, tenant_id)
        rows = session.execute(
            text(
                "SELECT id, approver_role FROM spike_approval_steps "
                "WHERE instance_id = :i ORDER BY step_index"
            ),
            {"i": str(instance.id)},
        ).all()
        version_hash = session.execute(
            text("SELECT content_hash FROM spike_workflow_versions WHERE id = :v"),
            {"v": str(version_id)},
        ).scalar_one()
    return FlowSetup(
        tenant_id=tenant_id,
        version_id=version_id,
        content_hash=str(version_hash),
        instance_id=instance.id,
        requester_id=requester,
        step_ids=[uuid.UUID(str(r[0])) for r in rows],
        step_roles=[str(r[1]) for r in rows],
    )


def approve_step(
    app_sf: sessionmaker[Session],
    flow: FlowSetup,
    step_index: int,
    now: datetime,
    *,
    decision: str = "approved",
    actor: uuid.UUID | None = None,
    idempotency_key: str | None = None,
) -> rt.DecisionResult:
    return rt.decide_step_command(
        app_sf,
        tenant_id=flow.tenant_id,
        step_id=flow.step_ids[step_index],
        actor_id=actor or uuid.uuid4(),
        approver_role=flow.step_roles[step_index],
        decision=decision,
        idempotency_key=idempotency_key or f"idem-{flow.instance_id}-{step_index}",
        request_id=f"req-decide-{step_index}",
        now=now,
    )


def approve_all(app_sf: sessionmaker[Session], flow: FlowSetup, now: datetime) -> rt.DecisionResult:
    result: rt.DecisionResult | None = None
    for index in range(len(flow.step_ids)):
        result = approve_step(app_sf, flow, index, now)
    assert result is not None
    return result


def count(session: Session, table: str, **where: str) -> int:
    clause = " AND ".join(f"{k} = :{k}" for k in where) or "TRUE"
    value = session.execute(
        text(f"SELECT count(*) FROM {table} WHERE {clause}"),  # noqa: S608 — test yardımcı
        dict(where.items()),
    ).scalar_one()
    return int(value)


def scoped_count(sf: sessionmaker[Session], tenant_id: uuid.UUID, table: str, **where: str) -> int:
    with sf() as session, session.begin():
        set_tenant_context(session, tenant_id)
        return count(session, table, **where)


def instance_row(
    sf: sessionmaker[Session], tenant_id: uuid.UUID, instance_id: uuid.UUID
) -> dict[str, Any]:
    with sf() as session, session.begin():
        set_tenant_context(session, tenant_id)
        row = (
            session.execute(
                text(
                    "SELECT status, current_node_id, version, context "
                    "FROM spike_instances WHERE id = :i"
                ),
                {"i": str(instance_id)},
            )
            .mappings()
            .one()
        )
        return dict(row)
