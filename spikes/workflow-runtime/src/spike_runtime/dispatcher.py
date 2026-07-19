"""Outbox dispatcher + idempotent inbox + persisted timer servisi.

- Claim: `FOR UPDATE SKIP LOCKED` + lease (`claim_expires_at`) → iki worker aynı işi
  alamaz; crash olan worker'ın lease'i dolunca iş YENİDEN alınabilir (kayıp iş yok).
- İşleme: inbox kaydı (`spike_processed_events`, PK ile) + side effect + outbox
  'processed' işareti AYNI transaction'da → duplicate teslim tek side effect üretir.
- Retry: bounded (MAX_ATTEMPTS) + exponential backoff; kalıcı başarısızlık 'failed'
  + audit incident. SONSUZ RETRY YOK. "Exactly once" İDDİASI YOK (at-least-once +
  idempotent consumer).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime.db import rowcount, set_tenant_context
from spike_runtime.logging_support import log_event

CONSUMER = "spike-worker"
MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 0.05

IdGen = Callable[[], uuid.UUID]


@dataclass(frozen=True)
class ClaimedEvent:
    outbox_id: int
    tenant_id: uuid.UUID
    event_id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    attempt: int


def claim_events(
    session: Session,
    *,
    worker_id: str,
    now: datetime,
    lease_seconds: float = 2.0,
    limit: int = 10,
) -> list[ClaimedEvent]:
    """Vadesi gelmiş (yeni veya lease'i dolmuş) event'leri kilitleyip lease yazar."""
    rows = (
        session.execute(
            text(
                "SELECT id, tenant_id, event_id, event_type, payload, attempt "
                "FROM spike_outbox_events "
                "WHERE status = 'pending' AND available_at <= :now "
                "AND (claim_expires_at IS NULL OR claim_expires_at <= :now) "
                "ORDER BY id LIMIT :limit FOR UPDATE SKIP LOCKED"
            ),
            {"now": now, "limit": limit},
        )
        .mappings()
        .all()
    )
    if not rows:
        return []
    session.execute(
        text(
            "UPDATE spike_outbox_events SET claimed_by = :worker, claim_expires_at = :expires "
            "WHERE id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
        {
            "worker": worker_id,
            "expires": now + timedelta(seconds=lease_seconds),
            "ids": [int(r["id"]) for r in rows],
        },
    )
    return [
        ClaimedEvent(
            outbox_id=int(r["id"]),
            tenant_id=uuid.UUID(str(r["tenant_id"])),
            event_id=uuid.UUID(str(r["event_id"])),
            event_type=str(r["event_type"]),
            payload=cast(dict[str, Any], r["payload"]),
            attempt=int(r["attempt"]),
        )
        for r in rows
    ]


def _handle_notification_requested(
    session: Session, event: ClaimedEvent, now: datetime, new_id: IdGen
) -> None:
    session.execute(
        text(
            "INSERT INTO spike_notifications "
            "(id, tenant_id, instance_id, recipient_role, message_key, source_event_id, "
            " created_at) "
            "VALUES (:id, :tenant, :instance, :role, :key, :event_id, :now)"
        ),
        {
            "id": str(new_id()),
            "tenant": str(event.tenant_id),
            "instance": str(event.payload["instance_id"]),
            "role": str(event.payload["recipient_role"]),
            "key": str(event.payload["message_key"]),
            "event_id": str(event.event_id),
            "now": now,
        },
    )


# Bilinen event tipleri; kayıtsız tipler side-effect üretmez (yalnız işaretlenir).
_HANDLERS: dict[str, Callable[[Session, ClaimedEvent, datetime, IdGen], None]] = {
    "notification.requested.v1": _handle_notification_requested,
}


def process_claimed(
    session: Session,
    event: ClaimedEvent,
    *,
    now: datetime,
    new_id: IdGen = uuid.uuid4,
    fail_handler: Callable[[ClaimedEvent], None] | None = None,
) -> str:
    """TEK transaction: inbox kaydı + side effect + 'processed' işareti.

    Dönen değer: 'processed' | 'duplicate'. `fail_handler` test amaçlı fault
    injection noktasıdır (side effect başarısızlığı simülasyonu).
    """
    set_tenant_context(session, event.tenant_id)
    inserted = session.execute(
        text(
            "INSERT INTO spike_processed_events (event_id, consumer, tenant_id, processed_at) "
            "VALUES (:event_id, :consumer, :tenant, :now) ON CONFLICT DO NOTHING"
        ),
        {
            "event_id": str(event.event_id),
            "consumer": CONSUMER,
            "tenant": str(event.tenant_id),
            "now": now,
        },
    )
    outcome = "duplicate"
    if rowcount(inserted) == 1:
        if fail_handler is not None:
            fail_handler(event)
        handler = _HANDLERS.get(event.event_type)
        if handler is not None:
            handler(session, event, now, new_id)
        outcome = "processed"
    session.execute(
        text(
            "UPDATE spike_outbox_events SET status = 'processed', processed_at = :now, "
            "claimed_by = NULL, claim_expires_at = NULL WHERE id = :id"
        ),
        {"now": now, "id": event.outbox_id},
    )
    log_event(
        "outbox.event_" + outcome,
        tenant_id=event.tenant_id,
        event_id=event.event_id,
        attempt=event.attempt,
        transition=f"pending->{outcome}",
        event_type=event.event_type,
    )
    return outcome


def mark_failed_attempt(
    session: Session,
    event: ClaimedEvent,
    *,
    now: datetime,
    error: str,
    new_id: IdGen = uuid.uuid4,
) -> str:
    """Bounded retry: backoff ile yeniden dener; limitte 'failed' + audit incident."""
    next_attempt = event.attempt + 1
    if next_attempt >= MAX_ATTEMPTS:
        session.execute(
            text(
                "UPDATE spike_outbox_events SET status = 'failed', attempt = :attempt, "
                "claimed_by = NULL, claim_expires_at = NULL WHERE id = :id"
            ),
            {"attempt": next_attempt, "id": event.outbox_id},
        )
        set_tenant_context(session, event.tenant_id)
        session.execute(
            text(
                "INSERT INTO spike_audit_events (id, tenant_id, event_id, actor_type, "
                "actor_id, action, resource_type, resource_id, occurred_at, request_id, "
                "reason, metadata) "
                "VALUES (:id, :tenant, :audit_event_id, 'system', :worker, "
                "'outbox.event_failed', 'outbox_event', :resource, :now, :request, :reason, "
                "CAST(:meta AS JSONB))"
            ),
            {
                "id": str(new_id()),
                "tenant": str(event.tenant_id),
                "audit_event_id": str(new_id()),
                "worker": CONSUMER,
                "resource": str(event.event_id),
                "now": now,
                "request": f"outbox-{event.outbox_id}",
                "reason": error[:500],
                "meta": json.dumps({"attempt": next_attempt, "event_type": event.event_type}),
            },
        )
        outcome = "failed"
    else:
        backoff = BACKOFF_BASE_SECONDS * (2**next_attempt)
        session.execute(
            text(
                "UPDATE spike_outbox_events SET attempt = :attempt, "
                "available_at = :available, claimed_by = NULL, claim_expires_at = NULL "
                "WHERE id = :id"
            ),
            {
                "attempt": next_attempt,
                "available": now + timedelta(seconds=backoff),
                "id": event.outbox_id,
            },
        )
        outcome = "retry_scheduled"
    log_event(
        "outbox.event_" + outcome,
        tenant_id=event.tenant_id,
        event_id=event.event_id,
        attempt=next_attempt,
        transition=f"pending->{outcome}",
    )
    return outcome


def fire_due_timers(
    session: Session,
    *,
    worker_id: str,
    now: datetime,
    limit: int = 10,
    new_id: IdGen = uuid.uuid4,
) -> int:
    """Vadesi gelen timer'ları SKIP LOCKED ile claim edip TAM BİR KEZ ateşler.

    Ateşleme = timer 'fired' + outbox'a notification.requested.v1 (AYNI transaction).
    """
    rows = (
        session.execute(
            text(
                "SELECT id, tenant_id, instance_id, purpose FROM spike_timers "
                "WHERE status = 'pending' AND fire_at <= :now "
                "ORDER BY fire_at LIMIT :limit FOR UPDATE SKIP LOCKED"
            ),
            {"now": now, "limit": limit},
        )
        .mappings()
        .all()
    )
    fired = 0
    for row in rows:
        # İkinci savunma (SPK-09): instance terminal ise timer ateşlenmez,
        # sessizce iptal edilir (engine zaten terminal geçişte iptal eder).
        set_tenant_context(session, uuid.UUID(str(row["tenant_id"])))
        instance_status = session.execute(
            text("SELECT status FROM spike_instances WHERE id = :id"),
            {"id": str(row["instance_id"])},
        ).scalar()
        if instance_status in ("completed", "rejected", "cancelled") or instance_status is None:
            session.execute(
                text(
                    "UPDATE spike_timers SET status = 'cancelled' "
                    "WHERE id = :id AND status = 'pending'"
                ),
                {"id": str(row["id"])},
            )
            continue
        updated = session.execute(
            text(
                "UPDATE spike_timers SET status = 'fired', fired_at = :now, fired_by = :worker "
                "WHERE id = :id AND status = 'pending'"
            ),
            {"now": now, "worker": worker_id, "id": str(row["id"])},
        )
        if rowcount(updated) != 1:  # yarışı kaybeden — ikinci ateşleme YOK
            continue
        session.execute(
            text(
                "INSERT INTO spike_outbox_events "
                "(tenant_id, event_id, event_type, payload, available_at, created_at) "
                "VALUES (:tenant, :event_id, 'notification.requested.v1', "
                "CAST(:payload AS JSONB), :now, :now)"
            ),
            {
                "tenant": str(row["tenant_id"]),
                "event_id": str(new_id()),
                "payload": json.dumps(
                    {
                        "instance_id": str(row["instance_id"]),
                        "tenant_id": str(row["tenant_id"]),
                        "recipient_role": "approver",
                        "message_key": str(row["purpose"]),
                    }
                ),
                "now": now,
            },
        )
        fired += 1
        log_event(
            "timer.fired",
            tenant_id=row["tenant_id"],
            workflow_instance_id=row["instance_id"],
            transition="pending->fired",
        )
    return fired


def run_pass(
    session_factory: sessionmaker[Session],
    *,
    worker_id: str,
    now: datetime,
    lease_seconds: float = 2.0,
    limit: int = 10,
    new_id: IdGen = uuid.uuid4,
    fail_handler: Callable[[ClaimedEvent], None] | None = None,
) -> dict[str, int]:
    """Tek dispatcher turu: timer'ları ateşle → event'leri claim et → işle."""
    stats = {"fired_timers": 0, "processed": 0, "duplicate": 0, "failed": 0, "retry": 0}
    with session_factory() as session, session.begin():
        stats["fired_timers"] = fire_due_timers(
            session, worker_id=worker_id, now=now, limit=limit, new_id=new_id
        )
    with session_factory() as session, session.begin():
        claimed = claim_events(
            session, worker_id=worker_id, now=now, lease_seconds=lease_seconds, limit=limit
        )
    for event in claimed:
        try:
            with session_factory() as session, session.begin():
                outcome = process_claimed(
                    session, event, now=now, new_id=new_id, fail_handler=fail_handler
                )
            stats[outcome] += 1
        except Exception as exc:  # worker tek event hatasıyla ÖLMEZ
            with session_factory() as session, session.begin():
                result = mark_failed_attempt(session, event, now=now, error=repr(exc))
            stats["failed" if result == "failed" else "retry"] += 1
    return stats
