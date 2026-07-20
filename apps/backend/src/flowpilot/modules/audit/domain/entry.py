"""AuditEntry — append-only denetim kaydı (FlowPilot ürün bileşeni).

Business transaction başarısızsa YAZILMAZ (aynı transaction'da). Hassas değerler
(token/secret/e-posta) yazılmaz; metadata sınırlı ve güvenlidir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from flowpilot.shared.identifiers import TenantId, UserId


class AuditEventType(StrEnum):
    """Denetlenen kritik aksiyonlar (ilk dilim)."""

    PURCHASE_REQUEST_CREATED = "purchase_request.created"
    WORKFLOW_STARTED = "workflow.started"
    APPROVAL_TASK_ASSIGNED = "approval.task_assigned"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_REJECTED = "workflow.rejected"
    ORGANIZATION_INVITATION_CREATED = "organization.invitation.created"
    ORGANIZATION_INVITATION_REVOKED = "organization.invitation.revoked"
    ORGANIZATION_INVITATION_EXPIRED = "organization.invitation.expired"
    ORGANIZATION_INVITATION_ACCEPTED = "organization.invitation.accepted"
    ORGANIZATION_MEMBERSHIP_JOINED = "organization.membership.joined"


@dataclass(frozen=True, slots=True)
class AuditEntryId:
    value: UUID


@dataclass(frozen=True)
class AuditEntry:
    """Bir denetim olayı. metadata YALNIZ güvenli, sınırlı alanlar içerir."""

    id: AuditEntryId
    tenant_id: TenantId
    aggregate_type: str
    aggregate_id: UUID
    event_type: AuditEventType
    occurred_at: datetime
    actor_user_id: UserId | None = None
    role_key: str | None = None
    task_id: UUID | None = None
    metadata: dict[str, str | int] = field(default_factory=dict)
