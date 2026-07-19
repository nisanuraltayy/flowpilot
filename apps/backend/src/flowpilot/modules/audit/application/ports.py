"""Audit application port'ları — DIŞARIYA sunulan yazma/okuma sözleşmeleri.

`AuditWriterPort` business modüller tarafından (composition root'ta wire edilerek)
AYNI transaction içinde çağrılır; presentation/API katmanı audit tablosuna DOĞRUDAN
insert YAPMAZ. Audit modülü hiçbir business modülünü import etmez.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from flowpilot.modules.audit.application.dto import AuditRecord, AuditTimelineItem


class AuditWriterPort(Protocol):
    """Append-only yazma; business state ile AYNI transaction'da (COMMIT ETMEZ).

    Girdi `AuditRecord` (application DTO): çağıran modül `audit.domain`'i import etmez.
    """

    def append(self, record: AuditRecord) -> None: ...


class AuditTimelineQueryPort(Protocol):
    """Bir aggregate'in kronolojik timeline'ı (tenant-scoped, RLS)."""

    def list_for_aggregate(
        self, *, tenant_id: UUID, aggregate_id: UUID, current_user_id: UUID
    ) -> list[AuditTimelineItem]: ...
