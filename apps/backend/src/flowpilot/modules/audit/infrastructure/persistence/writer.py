"""SQLAlchemy `AuditWriterPort` adapter'ı — append-only, COMMIT ETMEZ.

Session DIŞARIDAN verilir (compose transaction'ın parçası); böylece audit yazımı
business state ile AYNI transaction'da olur (SPK-11). `flush()` eder ki RLS/constraint
erken değerlendirilsin.
"""

from __future__ import annotations

from sqlalchemy import insert
from sqlalchemy.orm import Session

from flowpilot.modules.audit.application.dto import AuditRecord
from flowpilot.modules.audit.domain.entry import AuditEntry, AuditEntryId
from flowpilot.modules.audit.infrastructure.persistence.tables import audit_entries_table
from flowpilot.shared.identifiers import TenantId, UserId


class SqlAlchemyAuditWriter:
    """`AuditWriterPort` port'unu uygular."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, record: AuditRecord) -> None:
        # AuditRecord (application DTO) → AuditEntry (domain) → satır. Domain, güvenli
        # şekli tanımlar; adapter yalnız map + insert eder.
        entry = AuditEntry(
            id=AuditEntryId(record.event_id),
            tenant_id=TenantId(record.tenant_id),
            aggregate_type=record.aggregate_type,
            aggregate_id=record.aggregate_id,
            event_type=record.event_type,
            occurred_at=record.occurred_at,
            actor_user_id=UserId(record.actor_user_id) if record.actor_user_id else None,
            role_key=record.role_key,
            task_id=record.task_id,
            metadata=dict(record.metadata),
        )
        self._session.execute(
            insert(audit_entries_table).values(
                id=entry.id.value,
                tenant_id=entry.tenant_id.value,
                aggregate_type=entry.aggregate_type,
                aggregate_id=entry.aggregate_id,
                event_type=entry.event_type.value,
                actor_user_id=entry.actor_user_id.value if entry.actor_user_id else None,
                role_key=entry.role_key,
                task_id=entry.task_id,
                metadata=entry.metadata,
                occurred_at=entry.occurred_at,
            )
        )
        self._session.flush()
