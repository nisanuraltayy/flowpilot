"""Typed command/result/detail DTO'ları (provider-neutral; ORM/session içermez)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class CreatePurchaseRequestCommand:
    actor_user_id: UUID
    tenant_id: UUID
    title: str
    description: str | None
    amount_minor: int
    currency: str


@dataclass(frozen=True)
class CreatePurchaseRequestResult:
    purchase_request_id: UUID
    tenant_id: UUID
    workflow_instance_id: UUID
    status: str
    title: str
    amount_minor: int
    currency: str
    current_approval_role: str | None
    created_at: datetime


@dataclass(frozen=True)
class InboxItem:
    task_id: UUID
    purchase_request_id: UUID
    purchase_request_title: str
    amount_minor: int
    currency: str
    required_role: str
    status: str
    workflow_instance_id: UUID
    created_at: datetime
    due_at: datetime | None


@dataclass(frozen=True)
class PurchaseRequestListItem:
    purchase_request_id: UUID
    title: str
    amount_minor: int
    currency: str
    status: str
    current_approval_role: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PurchaseRequestDetail:
    purchase_request_id: UUID
    tenant_id: UUID
    requested_by_current_user: bool
    title: str
    description: str | None
    amount_minor: int
    currency: str
    status: str
    workflow_instance_id: UUID | None
    workflow_status: str | None
    current_approval_role: str | None
    created_at: datetime
    updated_at: datetime
