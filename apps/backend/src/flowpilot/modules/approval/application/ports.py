"""Approval application port'ları.

`ApprovalDecisionUnitOfWork`, decision akışının cross-module ATOMİK compose'u için
gereken TÜM repo'ları TEK session üzerinde birleştirir: runtime (WorkflowUnitOfWork)
+ approval_decisions + purchase_requests (status) + audit. Somut compose composition
root'ta (api/wiring.py) kurulur. Provider-neutral; SQLAlchemy görmez.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

from flowpilot.modules.approval.domain.models import ApprovalDecision, ApprovalRoleAssignment
from flowpilot.modules.audit.application.ports import AuditWriterPort
from flowpilot.modules.purchase_request.application.ports import PurchaseRequestRepository
from flowpilot.modules.workflow_runtime.application.port import WorkflowUnitOfWork


class ApprovalRoleAssignmentRepository(Protocol):
    def add_if_absent(self, assignment: ApprovalRoleAssignment) -> bool:
        """ON CONFLICT (tenant,role_key WHERE active) DO NOTHING; INSERT olduysa True."""
        ...


class ApprovalRoleAssignmentQuery(Protocol):
    def active_map(self, *, tenant_id: UUID) -> dict[str, UUID]:
        """Tenant'ın aktif role_key → assigned_user_id eşlemesi."""
        ...


class ApprovalDecisionRepository(Protocol):
    def add_if_absent(self, decision: ApprovalDecision) -> bool:
        """ON CONFLICT (task_id) DO NOTHING — task başına tek terminal karar. INSERT ise True."""
        ...

    def find_by_task(self, *, task_id: UUID) -> ApprovalDecision | None: ...


class ApprovalAssignmentUnitOfWork(Protocol):
    """Standalone assignment provisioning transaction (compose DEĞİL)."""

    approval_role_assignments: ApprovalRoleAssignmentRepository

    def __enter__(self) -> ApprovalAssignmentUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def set_actor_context(self, actor_user_id: UUID) -> None: ...

    def set_tenant_context(self, tenant_id: UUID) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class ApprovalDecisionUnitOfWork(WorkflowUnitOfWork, Protocol):
    """runtime UoW + approval_decisions + purchase_requests + audit — TEK transaction."""

    approval_decisions: ApprovalDecisionRepository
    purchase_requests: PurchaseRequestRepository
    audit: AuditWriterPort

    def __enter__(self) -> ApprovalDecisionUnitOfWork: ...
