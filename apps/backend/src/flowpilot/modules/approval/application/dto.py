"""Approval typed command/result DTO'ları (provider-neutral; ORM/session içermez)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class DecideApprovalTaskCommand:
    tenant_id: UUID
    actor_user_id: UUID
    task_id: UUID
    decision: str  # "approve" | "reject"
    comment: str | None
    idempotency_key: str


@dataclass(frozen=True)
class DecideApprovalTaskResult:
    task_id: UUID
    decision: str
    purchase_request_id: UUID
    purchase_request_status: str
    workflow_status: str
    next_approval_role: str | None
    decided_at: datetime
    duplicate: bool
