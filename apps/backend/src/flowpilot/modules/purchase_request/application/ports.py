"""Purchase Request application port'ları.

`PurchaseRequestUnitOfWork`, workflow_runtime'ın `WorkflowUnitOfWork` port'unu
GENİŞLETİR: böylece aynı transaction/session üzerinde HEM purchase_request HEM
workflow_runtime adapter'ları compose edilebilir (cross-module ATOMİK commit).
Bu, provider-neutral application sözleşmesidir; SQLAlchemy görmez.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from flowpilot.modules.purchase_request.application.dto import PurchaseRequestDetail
from flowpilot.modules.purchase_request.domain.purchase_request import PurchaseRequest
from flowpilot.modules.workflow_runtime.application.port import WorkflowUnitOfWork


class PurchaseRequestRepository(Protocol):
    """Aggregate-specific repository (generic repository YASAK)."""

    def add(self, request: PurchaseRequest) -> None: ...

    def update_checked(self, request: PurchaseRequest, *, expected_version: int) -> None:
        """Optimistic CAS: expected_version tutmazsa ConcurrencyConflictError."""
        ...


class PurchaseRequestUnitOfWork(WorkflowUnitOfWork, Protocol):
    """workflow_runtime UoW + purchase_requests repo — TEK session, TEK transaction."""

    purchase_requests: PurchaseRequestRepository

    def __enter__(self) -> PurchaseRequestUnitOfWork: ...


class PurchaseRequestReadQuery(Protocol):
    """Tek talebi RLS-scoped okuyan read model (detail için PR alanları)."""

    def get(
        self, *, tenant_id: UUID, purchase_request_id: UUID, current_user_id: UUID
    ) -> PurchaseRequestDetail | None: ...
