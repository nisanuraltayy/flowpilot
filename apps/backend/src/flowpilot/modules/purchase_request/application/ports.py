"""Purchase Request application port'ları.

`PurchaseRequestUnitOfWork`, workflow_runtime'ın `WorkflowUnitOfWork` port'unu
GENİŞLETİR: böylece aynı transaction/session üzerinde HEM purchase_request HEM
workflow_runtime adapter'ları compose edilebilir (cross-module ATOMİK commit).
Bu, provider-neutral application sözleşmesidir; SQLAlchemy görmez.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from flowpilot.modules.audit.application.ports import AuditWriterPort
from flowpilot.modules.purchase_request.application.dto import (
    InboxItem,
    PurchaseRequestDetail,
    PurchaseRequestListItem,
)
from flowpilot.modules.purchase_request.domain.purchase_request import PurchaseRequest
from flowpilot.modules.workflow_runtime.application.port import WorkflowUnitOfWork


class PurchaseRequestRepository(Protocol):
    """Aggregate-specific repository (generic repository YASAK)."""

    def add(self, request: PurchaseRequest) -> None: ...

    def update_checked(self, request: PurchaseRequest, *, expected_version: int) -> None:
        """Optimistic CAS: expected_version tutmazsa ConcurrencyConflictError."""
        ...

    def get_by_workflow_instance(self, workflow_instance_id: UUID) -> PurchaseRequest | None:
        """Bir workflow instance'a bağlı talebi döndürür (approval kararı akışı için)."""
        ...


class PurchaseRequestUnitOfWork(WorkflowUnitOfWork, Protocol):
    """workflow_runtime UoW + purchase_requests + audit — TEK session, TEK transaction.

    `audit`, talep oluşturma akışının (created/started/task_assigned) denetim
    kayıtlarını AYNI transaction'da yazması için compose edilir (timeline bütünlüğü).
    """

    purchase_requests: PurchaseRequestRepository
    audit: AuditWriterPort

    def __enter__(self) -> PurchaseRequestUnitOfWork: ...


class PurchaseRequestReadQuery(Protocol):
    """Tek talebi RLS-scoped okuyan read model (detail için PR alanları)."""

    def get(
        self, *, tenant_id: UUID, purchase_request_id: UUID, current_user_id: UUID
    ) -> PurchaseRequestDetail | None: ...

    def list_for_requester(
        self, *, tenant_id: UUID, requester_user_id: UUID, limit: int
    ) -> list[PurchaseRequestListItem]:
        """Yalnız actor'ın KENDİ oluşturduğu talepler, newest-first (MVP)."""
        ...


class TaskInboxQuery(Protocol):
    """Actor'a atanmış AKTİF onay task'larının inbox'ı (cross-module read model)."""

    def list_pending_for_user(
        self, *, tenant_id: UUID, user_id: UUID, limit: int
    ) -> list[InboxItem]: ...


class RoleAssigneeResolver(Protocol):
    """Workflow başlangıcında role→assignee eşlemesini SABİTLEMEK için (owner #4/#5).

    Approval modülünün adapter'ı bunu STRÜKTÜREL olarak uygular (approval → PR
    bağımlılığı yönünde; PR approval'ı IMPORT ETMEZ — circular import yok). Eksik
    roller aktif owner'a idempotent atanır; sonra aktif eşleme döner. Public
    role-management endpoint'i DEĞİLDİR.
    """

    def resolve_all(self, *, tenant_id: UUID, actor_user_id: UUID) -> dict[str, str]: ...
