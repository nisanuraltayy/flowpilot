"""Spike runtime çekirdeği — instance lifecycle, sequential approval, guard'lar.

Kurallar:
- Hiçbir fonksiyon COMMIT etmez; transaction sınırı çağırana aittir
  (state + outbox + audit atomikliği SPK-11'de böyle kanıtlanır).
- Zaman her fonksiyona tz-aware `now` parametresiyle enjekte edilir (naive YASAK).
- ID üretimi injectable (`new_id`).
- Para minor unit (int) + currency çifti olarak taşınır; float YASAK.
- Onay eşikleri/zincirleri workflow definition'dan okunur; kodda eşik YOK.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime.conditions import evaluate
from spike_runtime.db import rowcount, set_actor_context, set_tenant_context
from spike_runtime.definition import content_hash, node_by_id, validate_definition
from spike_runtime.errors import (
    DuplicateDecisionError,
    InvalidTransitionError,
    NotFoundError,
    SequenceOrderError,
    SpikeError,
    StaleVersionError,
    TerminalInstanceError,
    UnauthorizedApproverError,
)
from spike_runtime.logging_support import log_event

TERMINAL_INSTANCE_STATES = frozenset({"completed", "rejected", "cancelled"})
TERMINAL_STEP_STATES = frozenset({"approved", "rejected", "cancelled"})

IdGen = Callable[[], uuid.UUID]


def _require_utc(now: datetime) -> None:
    if now.tzinfo is None:
        raise SpikeError("naive datetime YASAK — tz-aware UTC bekleniyor")


@dataclass(frozen=True)
class PublishedVersion:
    id: uuid.UUID
    version_no: int
    content_hash: str


@dataclass(frozen=True)
class InstanceView:
    id: uuid.UUID
    status: str
    current_node_id: str
    version: int
    branch_explanation: str | None = None


@dataclass(frozen=True)
class DecisionResult:
    duplicate: bool
    decision: str
    step_id: uuid.UUID
    step_index: int
    instance_id: uuid.UUID
    instance_status: str
    activated_step_index: int | None


# ---------------------------------------------------------------- yardımcılar


def _insert_outbox(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    now: datetime,
    new_id: IdGen,
) -> uuid.UUID:
    event_id = new_id()
    session.execute(
        text(
            "INSERT INTO spike_outbox_events "
            "(tenant_id, event_id, event_type, payload, available_at, created_at) "
            "VALUES (:tenant, :event_id, :event_type, CAST(:payload AS JSONB), :now, :now)"
        ),
        {
            "tenant": str(tenant_id),
            "event_id": str(event_id),
            "event_type": event_type,
            "payload": json.dumps(payload),
            "now": now,
        },
    )
    return event_id


def _insert_audit(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    actor_type: str,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    request_id: str,
    now: datetime,
    new_id: IdGen,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.execute(
        text(
            "INSERT INTO spike_audit_events (id, tenant_id, event_id, actor_type, actor_id, "
            "action, resource_type, resource_id, occurred_at, request_id, reason, metadata) "
            "VALUES (:id, :tenant, :event_id, :actor_type, :actor_id, :action, "
            ":resource_type, :resource_id, :now, :request_id, :reason, CAST(:meta AS JSONB))"
        ),
        {
            "id": str(new_id()),
            "tenant": str(tenant_id),
            "event_id": str(new_id()),
            "actor_type": actor_type,
            "actor_id": actor_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "now": now,
            "request_id": request_id,
            "reason": reason,
            "meta": json.dumps(metadata or {}),
        },
    )


def _insert_node_execution(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    instance_id: uuid.UUID,
    node_id: str,
    node_type: str,
    now: datetime,
    new_id: IdGen,
    detail: dict[str, Any] | None = None,
) -> None:
    session.execute(
        text(
            "INSERT INTO spike_node_executions "
            "(id, tenant_id, instance_id, node_id, node_type, detail, executed_at) "
            "VALUES (:id, :tenant, :instance, :node_id, :node_type, CAST(:detail AS JSONB), :now)"
        ),
        {
            "id": str(new_id()),
            "tenant": str(tenant_id),
            "instance": str(instance_id),
            "node_id": node_id,
            "node_type": node_type,
            "detail": json.dumps(detail or {}),
            "now": now,
        },
    )


def _fetch_definition(session: Session, workflow_version_id: uuid.UUID) -> dict[str, Any]:
    row = session.execute(
        text("SELECT definition, version_no FROM spike_workflow_versions WHERE id = :id"),
        {"id": str(workflow_version_id)},
    ).first()
    if row is None:
        raise NotFoundError("workflow version bulunamadı")
    return cast(dict[str, Any], row[0])


# ------------------------------------------------------------------ komutlar


def publish_version(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    workflow_key: str,
    version_no: int,
    definition: dict[str, Any],
    actor_id: uuid.UUID,
    request_id: str,
    now: datetime,
    new_id: IdGen = uuid.uuid4,
) -> PublishedVersion:
    """Yeni immutable version yayınlar. Var olan version'a UPDATE yolu YOKTUR."""
    _require_utc(now)
    validate_definition(definition)
    version_id = new_id()
    digest = content_hash(definition)
    session.execute(
        text(
            "INSERT INTO spike_workflow_versions "
            "(id, tenant_id, workflow_key, version_no, definition, content_hash, published_at) "
            "VALUES (:id, :tenant, :key, :no, CAST(:definition AS JSONB), :hash, :now)"
        ),
        {
            "id": str(version_id),
            "tenant": str(tenant_id),
            "key": workflow_key,
            "no": version_no,
            "definition": json.dumps(definition, sort_keys=True),
            "hash": digest,
            "now": now,
        },
    )
    _insert_audit(
        session,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(actor_id),
        action="workflow.published",
        resource_type="workflow_version",
        resource_id=str(version_id),
        request_id=request_id,
        now=now,
        new_id=new_id,
        metadata={"version_no": version_no, "content_hash": digest},
    )
    log_event(
        "workflow.published",
        tenant_id=tenant_id,
        workflow_definition_version=version_no,
        transition="draft->published",
    )
    return PublishedVersion(id=version_id, version_no=version_no, content_hash=digest)


def start_instance(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    workflow_version_id: uuid.UUID,
    requester_id: uuid.UUID,
    request_id: str,
    now: datetime,
    new_id: IdGen = uuid.uuid4,
) -> InstanceView:
    """Instance TAM OLARAK bir published version'a sabitlenir (SPK-02)."""
    _require_utc(now)
    definition = _fetch_definition(session, workflow_version_id)
    start_node = next(n for n in definition["nodes"] if n["type"] == "start")
    form_node_id = str(start_node["next"])

    instance_id = new_id()
    session.execute(
        text(
            "INSERT INTO spike_instances "
            "(id, tenant_id, workflow_version_id, status, current_node_id, context, "
            " created_at, updated_at) "
            "VALUES (:id, :tenant, :version_id, 'waiting', :node, CAST(:ctx AS JSONB), "
            ":now, :now)"
        ),
        {
            "id": str(instance_id),
            "tenant": str(tenant_id),
            "version_id": str(workflow_version_id),
            "node": form_node_id,
            "ctx": json.dumps({"requester_id": str(requester_id)}),
            "now": now,
        },
    )
    _insert_node_execution(
        session,
        tenant_id=tenant_id,
        instance_id=instance_id,
        node_id=str(start_node["id"]),
        node_type="start",
        now=now,
        new_id=new_id,
    )
    event_id = _insert_outbox(
        session,
        tenant_id=tenant_id,
        event_type="instance.started.v1",
        payload={"instance_id": str(instance_id), "tenant_id": str(tenant_id)},
        now=now,
        new_id=new_id,
    )
    _insert_audit(
        session,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(requester_id),
        action="instance.started",
        resource_type="workflow_instance",
        resource_id=str(instance_id),
        request_id=request_id,
        now=now,
        new_id=new_id,
    )
    log_event(
        "instance.started",
        tenant_id=tenant_id,
        workflow_instance_id=instance_id,
        event_id=event_id,
        transition="pending->waiting(form)",
    )
    return InstanceView(id=instance_id, status="waiting", current_node_id=form_node_id, version=1)


def _fetch_instance_row(session: Session, instance_id: uuid.UUID) -> dict[str, Any]:
    row = (
        session.execute(
            text(
                "SELECT id, tenant_id, workflow_version_id, status, current_node_id, "
                "context, version FROM spike_instances WHERE id = :id"
            ),
            {"id": str(instance_id)},
        )
        .mappings()
        .first()
    )
    if row is None:
        # RLS cross-tenant erişimi de buraya düşürür: varlık bilgisi SIZDIRILMAZ.
        raise NotFoundError("workflow instance bulunamadı")
    return dict(row)


def submit_form(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    instance_id: uuid.UUID,
    form_data: dict[str, Any],
    actor_id: uuid.UUID,
    request_id: str,
    expected_version: int,
    now: datetime,
    new_id: IdGen = uuid.uuid4,
) -> InstanceView:
    """Form → condition → doğru approval zincirinin ilk adımını aktive eder."""
    _require_utc(now)
    inst = _fetch_instance_row(session, instance_id)
    if inst["status"] in TERMINAL_INSTANCE_STATES:
        raise TerminalInstanceError(f"terminal instance ilerletilemez: {inst['status']}")
    definition = _fetch_definition(session, uuid.UUID(str(inst["workflow_version_id"])))
    current_node = node_by_id(definition, str(inst["current_node_id"]))
    if inst["status"] != "waiting" or current_node["type"] != "form":
        raise InvalidTransitionError(
            f"form bu durumda gönderilemez: status={inst['status']}, node={current_node['type']}"
        )

    amount = form_data.get("amount_minor")
    currency = form_data.get("currency")
    if not isinstance(amount, int) or isinstance(amount, bool) or not isinstance(currency, str):
        raise InvalidTransitionError(
            "tutar minor unit (int) + currency (str) çifti olarak zorunludur"
        )

    context: dict[str, Any] = {**cast(dict[str, Any], inst["context"]), **form_data}
    condition_node = node_by_id(definition, str(current_node["next"]))
    branches = list(condition_node["config"]["branches"])
    branch = evaluate(branches, context)

    approval_node = node_by_id(definition, branch.next_node)
    chain = [str(role) for role in approval_node["config"]["approver_chain"]]

    # Optimistic guard ÖNCE: version CAS iki eşzamanlı submit'i burada serialize eder.
    # Kaybeden 0 satır günceller → StaleVersionError; HİÇBİR step/side effect yazmadan
    # rollback olur (aksi hâlde UNIQUE(step_index) ham IntegrityError üretirdi).
    updated = session.execute(
        text(
            "UPDATE spike_instances SET current_node_id = :node, context = CAST(:ctx AS JSONB), "
            "version = version + 1, updated_at = :now "
            "WHERE id = :id AND version = :expected AND status = 'waiting'"
        ),
        {
            "node": str(approval_node["id"]),
            "ctx": json.dumps(context),
            "now": now,
            "id": str(instance_id),
            "expected": expected_version,
        },
    )
    if rowcount(updated) != 1:
        raise StaleVersionError("instance eşzamanlı değişti — 409/412; sessiz overwrite YOK")

    for index, role in enumerate(chain):
        session.execute(
            text(
                "INSERT INTO spike_approval_steps "
                "(id, tenant_id, instance_id, step_index, approver_role, status, "
                " created_at, updated_at) "
                "VALUES (:id, :tenant, :instance, :idx, :role, :status, :now, :now)"
            ),
            {
                "id": str(new_id()),
                "tenant": str(tenant_id),
                "instance": str(instance_id),
                "idx": index,
                "role": role,
                "status": "active" if index == 0 else "pending",
                "now": now,
            },
        )

    for node, detail in (
        (current_node, {"fields": sorted(form_data)}),
        (condition_node, {"branch": branch.branch_id, "explanation": branch.explanation}),
        (approval_node, {"chain": chain, "activated_step_index": 0}),
    ):
        _insert_node_execution(
            session,
            tenant_id=tenant_id,
            instance_id=instance_id,
            node_id=str(node["id"]),
            node_type=str(node["type"]),
            now=now,
            new_id=new_id,
            detail=detail,
        )

    event_id = _insert_outbox(
        session,
        tenant_id=tenant_id,
        event_type="instance.form_submitted.v1",
        payload={
            "instance_id": str(instance_id),
            "tenant_id": str(tenant_id),
            "branch": branch.branch_id,
        },
        now=now,
        new_id=new_id,
    )
    _insert_audit(
        session,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(actor_id),
        action="form.submitted",
        resource_type="workflow_instance",
        resource_id=str(instance_id),
        request_id=request_id,
        now=now,
        new_id=new_id,
        reason=branch.explanation,
        metadata={"branch": branch.branch_id, "approver_chain": chain},
    )
    log_event(
        "form.submitted",
        tenant_id=tenant_id,
        workflow_instance_id=instance_id,
        event_id=event_id,
        transition=f"form->{branch.next_node}",
    )
    return InstanceView(
        id=instance_id,
        status="waiting",
        current_node_id=str(approval_node["id"]),
        version=expected_version + 1,
        branch_explanation=branch.explanation,
    )


def _idempotent_replay(
    session: Session,
    *,
    step_id: uuid.UUID,
    actor_id: uuid.UUID,
    idempotency_key: str,
    step_index: int,
    instance_id: uuid.UUID,
) -> DecisionResult:
    row = (
        session.execute(
            text(
                "SELECT decision, actor_id, idempotency_key "
                "FROM spike_approval_decisions WHERE step_id = :sid"
            ),
            {"sid": str(step_id)},
        )
        .mappings()
        .first()
    )
    if (
        row is not None
        and str(row["actor_id"]) == str(actor_id)
        and row["idempotency_key"] == idempotency_key
    ):
        inst = _fetch_instance_row(session, instance_id)
        return DecisionResult(
            duplicate=True,
            decision=str(row["decision"]),
            step_id=step_id,
            step_index=step_index,
            instance_id=instance_id,
            instance_status=str(inst["status"]),
            activated_step_index=None,
        )
    raise DuplicateDecisionError(
        "bu approval step için zaten terminal bir karar var (tek geçerli karar kuralı)"
    )


def decide_step(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    step_id: uuid.UUID,
    actor_id: uuid.UUID,
    approver_role: str,
    decision: str,
    idempotency_key: str,
    request_id: str,
    now: datetime,
    expected_step_version: int | None = None,
    new_id: IdGen = uuid.uuid4,
) -> DecisionResult:
    """Tek transaction: karar + step geçişi + instance geçişi + outbox + audit."""
    _require_utc(now)
    if decision not in ("approved", "rejected"):
        raise InvalidTransitionError(f"geçersiz karar: {decision!r}")

    row = (
        session.execute(
            text(
                "SELECT s.id, s.tenant_id, s.instance_id, s.step_index, s.approver_role, "
                "s.status, s.version, i.status AS instance_status, "
                "i.version AS instance_version, i.workflow_version_id, i.current_node_id "
                "FROM spike_approval_steps s "
                "JOIN spike_instances i ON i.id = s.instance_id "
                "WHERE s.id = :sid"
            ),
            {"sid": str(step_id)},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise NotFoundError("approval step bulunamadı")

    instance_id = uuid.UUID(str(row["instance_id"]))
    step_index = int(row["step_index"])

    if str(row["instance_status"]) in TERMINAL_INSTANCE_STATES:
        raise TerminalInstanceError(
            f"terminal instance ({row['instance_status']}) üzerinde karar verilemez"
        )
    if str(row["status"]) == "pending":
        raise SequenceOrderError(
            f"step {step_index} henüz aktif değil — önceki adım tamamlanmadan karar verilemez"
        )
    if str(row["status"]) in TERMINAL_STEP_STATES:
        return _idempotent_replay(
            session,
            step_id=step_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            step_index=step_index,
            instance_id=instance_id,
        )
    if str(row["approver_role"]) != approver_role:
        raise UnauthorizedApproverError(
            f"step {step_index} rolü {row['approver_role']!r}; {approver_role!r} karar veremez"
        )

    expected = int(row["version"]) if expected_step_version is None else expected_step_version
    updated = session.execute(
        text(
            "UPDATE spike_approval_steps SET status = :new_status, version = version + 1, "
            "updated_at = :now WHERE id = :sid AND version = :expected AND status = 'active'"
        ),
        {"new_status": decision, "now": now, "sid": str(step_id), "expected": expected},
    )
    if rowcount(updated) != 1:
        fresh = session.execute(
            text("SELECT status FROM spike_approval_steps WHERE id = :sid"),
            {"sid": str(step_id)},
        ).scalar_one()
        if str(fresh) in TERMINAL_STEP_STATES:
            return _idempotent_replay(
                session,
                step_id=step_id,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                step_index=step_index,
                instance_id=instance_id,
            )
        raise StaleVersionError("approval step eşzamanlı değişti — 409/412")

    # DB-düzeyi ikinci savunma: UNIQUE(step_id) — uygulama yarışı kaybederse
    # IntegrityError üretir; komut sınırında kontrollü sonuca çevrilir.
    session.execute(
        text(
            "INSERT INTO spike_approval_decisions "
            "(id, tenant_id, step_id, instance_id, actor_id, decision, idempotency_key, "
            " decided_at) "
            "VALUES (:id, :tenant, :sid, :instance, :actor, :decision, :key, :now)"
        ),
        {
            "id": str(new_id()),
            "tenant": str(tenant_id),
            "sid": str(step_id),
            "instance": str(instance_id),
            "actor": str(actor_id),
            "decision": decision,
            "key": idempotency_key,
            "now": now,
        },
    )

    activated: int | None = None
    instance_status = "waiting"
    instance_version = int(row["instance_version"])

    if decision == "approved":
        next_step = session.execute(
            text(
                "SELECT id FROM spike_approval_steps "
                "WHERE instance_id = :instance AND step_index = :idx"
            ),
            {"instance": str(instance_id), "idx": step_index + 1},
        ).first()
        if next_step is not None:
            promoted = session.execute(
                text(
                    "UPDATE spike_approval_steps SET status = 'active', version = version + 1, "
                    "updated_at = :now WHERE id = :sid AND status = 'pending'"
                ),
                {"now": now, "sid": str(next_step[0])},
            )
            if rowcount(promoted) != 1:
                raise InvalidTransitionError("sonraki step 'pending' durumunda değil")
            activated = step_index + 1
        else:
            instance_status = _finish_instance(
                session,
                tenant_id=tenant_id,
                instance_id=instance_id,
                instance_version=instance_version,
                workflow_version_id=uuid.UUID(str(row["workflow_version_id"])),
                current_node_id=str(row["current_node_id"]),
                now=now,
                new_id=new_id,
            )
    else:
        session.execute(
            text(
                "UPDATE spike_approval_steps SET status = 'cancelled', version = version + 1, "
                "updated_at = :now WHERE instance_id = :instance AND status = 'pending'"
            ),
            {"now": now, "instance": str(instance_id)},
        )
        session.execute(
            text(
                "UPDATE spike_timers SET status = 'cancelled' "
                "WHERE instance_id = :instance AND status = 'pending'"
            ),
            {"instance": str(instance_id)},
        )
        _terminal_instance_update(
            session,
            instance_id=instance_id,
            instance_version=instance_version,
            new_status="rejected",
            now=now,
        )
        _notify_requester(
            session,
            tenant_id=tenant_id,
            instance_id=instance_id,
            workflow_version_id=uuid.UUID(str(row["workflow_version_id"])),
            now=now,
            new_id=new_id,
        )
        instance_status = "rejected"

    event_id = _insert_outbox(
        session,
        tenant_id=tenant_id,
        event_type="approval.decided.v1",
        payload={
            "instance_id": str(instance_id),
            "tenant_id": str(tenant_id),
            "step_id": str(step_id),
            "step_index": step_index,
            "decision": decision,
        },
        now=now,
        new_id=new_id,
    )
    _insert_audit(
        session,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(actor_id),
        action="approval.decided",
        resource_type="approval_step",
        resource_id=str(step_id),
        request_id=request_id,
        now=now,
        new_id=new_id,
        metadata={"decision": decision, "step_index": step_index, "role": approver_role},
    )
    log_event(
        "approval.decided",
        tenant_id=tenant_id,
        workflow_instance_id=instance_id,
        task_id=step_id,
        event_id=event_id,
        transition=f"active->{decision}",
    )
    return DecisionResult(
        duplicate=False,
        decision=decision,
        step_id=step_id,
        step_index=step_index,
        instance_id=instance_id,
        instance_status=instance_status,
        activated_step_index=activated,
    )


def _terminal_instance_update(
    session: Session,
    *,
    instance_id: uuid.UUID,
    instance_version: int,
    new_status: str,
    now: datetime,
) -> None:
    updated = session.execute(
        text(
            "UPDATE spike_instances SET status = :status, version = version + 1, "
            "updated_at = :now "
            "WHERE id = :id AND version = :expected AND status IN ('running','waiting')"
        ),
        {"status": new_status, "now": now, "id": str(instance_id), "expected": instance_version},
    )
    if rowcount(updated) != 1:
        raise StaleVersionError("instance eşzamanlı değişti — 409/412")


def _notify_requester(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    instance_id: uuid.UUID,
    workflow_version_id: uuid.UUID,
    now: datetime,
    new_id: IdGen,
) -> None:
    definition = _fetch_definition(session, workflow_version_id)
    notify_node = next(n for n in definition["nodes"] if n["type"] == "notification")
    _insert_outbox(
        session,
        tenant_id=tenant_id,
        event_type="notification.requested.v1",
        payload={
            "instance_id": str(instance_id),
            "tenant_id": str(tenant_id),
            "recipient_role": str(notify_node["config"]["recipient_role"]),
            "message_key": str(notify_node["config"]["message_key"]),
        },
        now=now,
        new_id=new_id,
    )


def _finish_instance(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    instance_id: uuid.UUID,
    instance_version: int,
    workflow_version_id: uuid.UUID,
    current_node_id: str,
    now: datetime,
    new_id: IdGen,
) -> str:
    definition = _fetch_definition(session, workflow_version_id)
    approval_node = node_by_id(definition, current_node_id)
    notify_node = node_by_id(definition, str(approval_node["next"]))
    end_node = node_by_id(definition, str(notify_node["next"]))
    # Invariant §36.1/10: terminal geçişte açık timer'lar kapatılır —
    # geciken timer tamamlanmış süreci "diriltemez" (SPK-09/c).
    session.execute(
        text(
            "UPDATE spike_timers SET status = 'cancelled' "
            "WHERE instance_id = :instance AND status = 'pending'"
        ),
        {"instance": str(instance_id)},
    )
    for node, detail in (
        (approval_node, {"result": "all_steps_approved"}),
        (notify_node, {"intent": "queued_via_outbox"}),
        (end_node, {}),
    ):
        _insert_node_execution(
            session,
            tenant_id=tenant_id,
            instance_id=instance_id,
            node_id=str(node["id"]),
            node_type=str(node["type"]),
            now=now,
            new_id=new_id,
            detail=dict(detail),
        )
    _notify_requester(
        session,
        tenant_id=tenant_id,
        instance_id=instance_id,
        workflow_version_id=workflow_version_id,
        now=now,
        new_id=new_id,
    )
    updated = session.execute(
        text(
            "UPDATE spike_instances SET status = 'completed', current_node_id = :node, "
            "version = version + 1, updated_at = :now "
            "WHERE id = :id AND version = :expected AND status = 'waiting'"
        ),
        {
            "node": str(end_node["id"]),
            "now": now,
            "id": str(instance_id),
            "expected": instance_version,
        },
    )
    if rowcount(updated) != 1:
        raise StaleVersionError("instance eşzamanlı değişti — 409/412")
    return "completed"


def cancel_instance(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    instance_id: uuid.UUID,
    actor_id: uuid.UUID,
    request_id: str,
    expected_version: int,
    now: datetime,
    new_id: IdGen = uuid.uuid4,
) -> None:
    """Cancel: açık step/timer'lar kapatılır (invariant §36.1/10)."""
    _require_utc(now)
    inst = _fetch_instance_row(session, instance_id)
    if inst["status"] in TERMINAL_INSTANCE_STATES:
        raise TerminalInstanceError(f"terminal instance iptal edilemez: {inst['status']}")
    session.execute(
        text(
            "UPDATE spike_approval_steps SET status = 'cancelled', version = version + 1, "
            "updated_at = :now "
            "WHERE instance_id = :instance AND status IN ('pending','active')"
        ),
        {"now": now, "instance": str(instance_id)},
    )
    session.execute(
        text(
            "UPDATE spike_timers SET status = 'cancelled' "
            "WHERE instance_id = :instance AND status = 'pending'"
        ),
        {"instance": str(instance_id)},
    )
    _terminal_instance_update(
        session,
        instance_id=instance_id,
        instance_version=expected_version,
        new_status="cancelled",
        now=now,
    )
    _insert_outbox(
        session,
        tenant_id=tenant_id,
        event_type="instance.cancelled.v1",
        payload={"instance_id": str(instance_id), "tenant_id": str(tenant_id)},
        now=now,
        new_id=new_id,
    )
    _insert_audit(
        session,
        tenant_id=tenant_id,
        actor_type="user",
        actor_id=str(actor_id),
        action="instance.cancelled",
        resource_type="workflow_instance",
        resource_id=str(instance_id),
        request_id=request_id,
        now=now,
        new_id=new_id,
    )


def schedule_timer(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    instance_id: uuid.UUID,
    purpose: str,
    fire_at: datetime,
    now: datetime,
    new_id: IdGen = uuid.uuid4,
) -> uuid.UUID:
    """Timer VERİTABANINDA yaşar (in-memory timer YASAK)."""
    _require_utc(now)
    _require_utc(fire_at)
    timer_id = new_id()
    session.execute(
        text(
            "INSERT INTO spike_timers (id, tenant_id, instance_id, purpose, fire_at, created_at) "
            "VALUES (:id, :tenant, :instance, :purpose, :fire_at, :now)"
        ),
        {
            "id": str(timer_id),
            "tenant": str(tenant_id),
            "instance": str(instance_id),
            "purpose": purpose,
            "fire_at": fire_at,
            "now": now,
        },
    )
    return timer_id


# ------------------------------------------------- komut sınırı (API benzeri)

_DENIED_ERRORS = (
    SequenceOrderError,
    TerminalInstanceError,
    DuplicateDecisionError,
    StaleVersionError,
    UnauthorizedApproverError,
    NotFoundError,  # cross-tenant/IDOR denemesi de güvenlik log'una yazılır
)


def decide_step_command(
    session_factory: sessionmaker[Session],
    *,
    tenant_id: uuid.UUID,
    step_id: uuid.UUID,
    actor_id: uuid.UUID,
    approver_role: str,
    decision: str,
    idempotency_key: str,
    request_id: str,
    now: datetime,
    expected_step_version: int | None = None,
    new_id: IdGen = uuid.uuid4,
) -> DecisionResult:
    """API katmanının yapacağı gibi: tek transaction, kontrollü hata eşlemesi.

    - Guard reddi → AYRI transaction'da güvenlik audit kaydı, sonra hata yükselir.
    - UNIQUE(step_id) yarış kaybı → kontrollü DuplicateDecision/idempotent sonuç.
    """
    try:
        with session_factory() as session, session.begin():
            set_tenant_context(session, tenant_id)
            set_actor_context(session, str(actor_id))
            return decide_step(
                session,
                tenant_id=tenant_id,
                step_id=step_id,
                actor_id=actor_id,
                approver_role=approver_role,
                decision=decision,
                idempotency_key=idempotency_key,
                request_id=request_id,
                now=now,
                expected_step_version=expected_step_version,
                new_id=new_id,
            )
    except IntegrityError:
        with session_factory() as session, session.begin():
            set_tenant_context(session, tenant_id)
            row = (
                session.execute(
                    text(
                        "SELECT instance_id, step_index FROM spike_approval_steps WHERE id = :sid"
                    ),
                    {"sid": str(step_id)},
                )
                .mappings()
                .one()
            )
            return _idempotent_replay(
                session,
                step_id=step_id,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                step_index=int(row["step_index"]),
                instance_id=uuid.UUID(str(row["instance_id"])),
            )
    except _DENIED_ERRORS as exc:
        with session_factory() as session, session.begin():
            set_tenant_context(session, tenant_id)
            set_actor_context(session, str(actor_id))
            _insert_audit(
                session,
                tenant_id=tenant_id,
                actor_type="user",
                actor_id=str(actor_id),
                action="approval.decision_denied",
                resource_type="approval_step",
                resource_id=str(step_id),
                request_id=request_id,
                now=now,
                new_id=new_id,
                reason=f"{type(exc).__name__}: {exc}",
            )
        log_event(
            "approval.decision_denied",
            tenant_id=tenant_id,
            task_id=step_id,
            transition="denied",
            reason=type(exc).__name__,
        )
        raise
