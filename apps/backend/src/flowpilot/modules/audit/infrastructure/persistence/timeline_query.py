"""SQLAlchemy `AuditTimelineQueryPort` adapter'ı — RLS-scoped kronolojik timeline.

Kendi kısa-ömürlü session'ını açar, tenant context set eder. Başka tenant'ın
timeline'ı görünmez (RLS). Kullanıcıya güvenli mesaj üretir; ham metadata sınırlıdır.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.audit.application.dto import AuditTimelineItem
from flowpilot.modules.audit.domain.entry import AuditEventType
from flowpilot.modules.audit.infrastructure.persistence.tables import audit_entries_table

_MESSAGES: dict[str, str] = {
    AuditEventType.PURCHASE_REQUEST_CREATED.value: "Satın alma talebi oluşturuldu.",
    AuditEventType.WORKFLOW_STARTED.value: "Onay süreci başlatıldı.",
    AuditEventType.APPROVAL_TASK_ASSIGNED.value: "Onay adımı atandı.",
    AuditEventType.APPROVAL_APPROVED.value: "Onay adımı onaylandı.",
    AuditEventType.APPROVAL_REJECTED.value: "Onay adımı reddedildi.",
    AuditEventType.WORKFLOW_COMPLETED.value: "Onay süreci tamamlandı.",
    AuditEventType.WORKFLOW_REJECTED.value: "Onay süreci reddedildi.",
}


class SqlAlchemyAuditTimelineQuery:
    """`AuditTimelineQueryPort` port'unu uygular."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_for_aggregate(
        self, *, tenant_id: UUID, aggregate_id: UUID, current_user_id: UUID
    ) -> list[AuditTimelineItem]:
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :v, true)"),
                {"v": str(tenant_id)},
            )
            rows = (
                session.execute(
                    select(audit_entries_table)
                    .where(audit_entries_table.c.aggregate_id == aggregate_id)
                    # (occurred_at, seq): seq deterministik tiebreaker (insertion order).
                    .order_by(audit_entries_table.c.occurred_at, audit_entries_table.c.seq)
                )
                .mappings()
                .all()
            )
        return [
            AuditTimelineItem(
                event_type=str(row["event_type"]),
                occurred_at=row["occurred_at"],
                actor_is_current_user=row["actor_user_id"] == current_user_id,
                role_key=row["role_key"],
                task_id=row["task_id"],
                message=_MESSAGES.get(str(row["event_type"]), str(row["event_type"])),
            )
            for row in rows
        ]
