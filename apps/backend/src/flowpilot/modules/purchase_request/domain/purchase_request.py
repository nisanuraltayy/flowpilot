"""PurchaseRequest aggregate + durum + domain event.

İlk dikey dilim: create → workflow instance'a bağlan → `in_approval`. Approval
kararı/inbox sonraki aşamadadır. Aggregate immutable'dır (frozen); geçişler yeni
örnek döndürür.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from flowpilot.modules.purchase_request.domain.errors import (
    InvalidPurchaseRequestTransitionError,
)
from flowpilot.modules.purchase_request.domain.identifiers import PurchaseRequestId
from flowpilot.modules.purchase_request.domain.money import Money
from flowpilot.modules.purchase_request.domain.value_objects import (
    PurchaseRequestDescription,
    PurchaseRequestTitle,
)
from flowpilot.shared.identifiers import TenantId, UserId


class PurchaseRequestStatus(StrEnum):
    """Purchase request yaşam döngüsü (ilk dilim: draft → in_approval)."""

    DRAFT = "draft"
    IN_APPROVAL = "in_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class PurchaseRequestCreated:
    """Talep oluşturuldu domain event'i (workflow'a bağlanmadan önce)."""

    purchase_request_id: PurchaseRequestId
    tenant_id: TenantId
    requested_by: UserId
    amount_minor: int
    currency: str
    occurred_at: datetime


@dataclass(frozen=True)
class PurchaseRequest:
    """Satın alma talebi aggregate'i."""

    id: PurchaseRequestId
    tenant_id: TenantId
    requested_by: UserId
    title: PurchaseRequestTitle
    description: PurchaseRequestDescription
    money: Money
    status: PurchaseRequestStatus
    workflow_instance_id: UUID | None
    created_at: datetime
    updated_at: datetime
    version: int

    @classmethod
    def create(
        cls,
        *,
        id: PurchaseRequestId,
        tenant_id: TenantId,
        requested_by: UserId,
        title: PurchaseRequestTitle,
        description: PurchaseRequestDescription,
        money: Money,
        created_at: datetime,
    ) -> tuple[PurchaseRequest, PurchaseRequestCreated]:
        """DRAFT bir talep (henüz workflow'a bağlanmamış) + created event üretir."""
        request = cls(
            id=id,
            tenant_id=tenant_id,
            requested_by=requested_by,
            title=title,
            description=description,
            money=money,
            status=PurchaseRequestStatus.DRAFT,
            workflow_instance_id=None,
            created_at=created_at,
            updated_at=created_at,
            version=1,
        )
        event = PurchaseRequestCreated(
            purchase_request_id=id,
            tenant_id=tenant_id,
            requested_by=requested_by,
            amount_minor=money.amount_minor,
            currency=money.currency,
            occurred_at=created_at,
        )
        return request, event

    def attach_workflow(self, *, workflow_instance_id: UUID, now: datetime) -> PurchaseRequest:
        """DRAFT → IN_APPROVAL: workflow instance'a bağlanır (atomik akışın parçası)."""
        if self.status is not PurchaseRequestStatus.DRAFT:
            raise InvalidPurchaseRequestTransitionError(
                f"workflow yalnız DRAFT talebe bağlanabilir (mevcut: {self.status.value})"
            )
        return replace(
            self,
            workflow_instance_id=workflow_instance_id,
            status=PurchaseRequestStatus.IN_APPROVAL,
            updated_at=now,
            version=self.version + 1,
        )

    def approve(self, *, now: datetime) -> PurchaseRequest:
        """IN_APPROVAL → APPROVED (son onay; approval kararıyla aynı transaction)."""
        if self.status is not PurchaseRequestStatus.IN_APPROVAL:
            raise InvalidPurchaseRequestTransitionError(
                f"yalnız IN_APPROVAL talep approved olabilir (mevcut: {self.status.value})"
            )
        return replace(
            self, status=PurchaseRequestStatus.APPROVED, updated_at=now, version=self.version + 1
        )

    def reject(self, *, now: datetime) -> PurchaseRequest:
        """IN_APPROVAL → REJECTED."""
        if self.status is not PurchaseRequestStatus.IN_APPROVAL:
            raise InvalidPurchaseRequestTransitionError(
                f"yalnız IN_APPROVAL talep rejected olabilir (mevcut: {self.status.value})"
            )
        return replace(
            self, status=PurchaseRequestStatus.REJECTED, updated_at=now, version=self.version + 1
        )
