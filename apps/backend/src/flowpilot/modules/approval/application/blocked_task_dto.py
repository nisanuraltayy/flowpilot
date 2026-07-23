"""Blocked approval task listeleme/çözümleme DTO'ları (application sınırı; primitive + UUID).

Hassas identity (provider_subject / auth_provider / JWT) DÖNMEZ. Blocked task = self-approval
nedeniyle uygun onaycısı olmayan adım (FP-E06-009).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class BlockedApprovalTaskView:
    task_id: UUID
    purchase_request_id: UUID | None
    approver_role: str
    status: str
    blocked_reason: str | None
    requester_user_id: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ResolveBlockedTaskCommand:
    tenant_id: UUID
    actor_user_id: UUID
    task_id: UUID


@dataclass(frozen=True)
class ResolveBlockedTaskResult:
    task_id: UUID
    purchase_request_id: UUID | None
    approver_role: str
    status: str
    assigned_user_id: UUID
    version: int
