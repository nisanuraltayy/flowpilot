"""Audit application DTO'ları — DIŞARI SUNULAN yazma/okuma sözleşmeleri.

`AuditRecord` + `AuditEventType`, business modüllerin audit yazarken kullandığı
provider-neutral CONTRACT'tır: böylece başka bir bounded context `audit.domain`'i
DOĞRUDAN import etmez (dependency-rules §2 — cross-context domain importu YASAK).
`AuditEventType` buradan re-export edilir (kanonik tanım audit.domain'de).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from flowpilot.modules.audit.domain.entry import AuditEventType

__all__ = ["AuditEventType", "AuditRecord", "AuditTimelineItem"]


@dataclass(frozen=True)
class AuditRecord:
    """Bir audit olayının yazım isteği (application sınırı; primitive + UUID).

    `event_id` çağıranın injectable IdGeneratorPort'undan gelir (deterministik test).
    metadata YALNIZ güvenli, sınırlı alanlar içerir (token/secret/e-posta YAZILMAZ).
    """

    event_id: UUID
    tenant_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_type: AuditEventType
    occurred_at: datetime
    actor_user_id: UUID | None = None
    role_key: str | None = None
    task_id: UUID | None = None
    metadata: dict[str, str | int] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditTimelineItem:
    event_type: str
    occurred_at: datetime
    actor_is_current_user: bool
    role_key: str | None
    task_id: UUID | None
    message: str
