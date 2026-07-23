"""Blocked approval task listeleme/çözümleme port'ları (aggregate-specific).

`ResolveBlockedTaskUnitOfWork` runtime task transition + aktif role assignment okuması +
purchase request (pr_id) + audit'i TEK transaction'da birleştirir (compose; wiring'de
kurulur). Cross-module read'ler composition root'ta wire edilir; approval, workflow/
organization infrastructure'ını DOĞRUDAN import etmez.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from flowpilot.modules.approval.application.blocked_task_dto import BlockedApprovalTaskView
from flowpilot.modules.audit.application.ports import AuditWriterPort
from flowpilot.modules.purchase_request.application.ports import PurchaseRequestRepository
from flowpilot.modules.workflow_runtime.application.port import WorkflowUnitOfWork


class BlockedApprovalTaskListQuery(Protocol):
    """Tenant'ın blocked approval task'larını (pr + requester ile) deterministik listeler."""

    def list_blocked(self, *, tenant_id: UUID, limit: int) -> list[BlockedApprovalTaskView]: ...


class ActiveRoleAssignmentReader(Protocol):
    """Cross-module READ: bir approval role_key'in AKTİF atanmış kullanıcısı (compose session)."""

    def find_active_user(self, *, tenant_id: UUID, role_key: str) -> UUID | None: ...


class ResolveBlockedTaskUnitOfWork(WorkflowUnitOfWork, Protocol):
    """runtime UoW + aktif role assignment reader + purchase_requests + audit — TEK tx."""

    role_assignments: ActiveRoleAssignmentReader
    purchase_requests: PurchaseRequestRepository
    audit: AuditWriterPort

    def __enter__(self) -> ResolveBlockedTaskUnitOfWork: ...
