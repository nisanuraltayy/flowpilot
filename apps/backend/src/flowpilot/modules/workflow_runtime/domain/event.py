"""WorkflowEvent — append-only runtime event (timeline + node execution kaydı).

İki farklı amaç, iki farklı kalıcılık:
- WorkflowEvent: instance TIMELINE'ı (node yürütme, karar, geçiş) — append-only.
- IntegrationEvent (outbox): modül sınırını geçecek, dispatch edilecek mesaj.

İkisi de state değişikliğiyle AYNI transaction'da yazılır (SPK-11, ADR-007).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from flowpilot.modules.workflow_runtime.domain.identifiers import (
    WorkflowEventId,
    WorkflowInstanceId,
)
from flowpilot.shared.identifiers import TenantId


@dataclass(frozen=True)
class WorkflowEvent:
    """Instance timeline'ında append-only bir kayıt (human/system ayrımı `actor_type`)."""

    id: WorkflowEventId
    tenant_id: TenantId
    instance_id: WorkflowInstanceId
    event_type: str
    occurred_at: datetime
    node_id: str | None = None
    actor_type: str = "system"
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IntegrationEvent:
    """Outbox'a yazılacak, dispatch edilecek versiyonlu integration event."""

    id: WorkflowEventId
    tenant_id: TenantId
    event_type: str
    payload: dict[str, Any]
    available_at: datetime
