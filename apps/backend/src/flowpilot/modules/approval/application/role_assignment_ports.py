"""Approval rol atama application port'ları (aggregate-specific; generic repository YASAK).

`ApprovalRoleAssignmentUpdateUnitOfWork` tek transaction'da rol atama yönetimi + hedef
üyelik okuması + audit'i birleştirir (compose; wiring'de kurulur). `target_memberships`
cross-module bir READ contract'tır — approval, organization infrastructure'ını DOĞRUDAN
import etmez; sorgu composition root'ta wire edilir.
"""

from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from flowpilot.modules.approval.application.role_assignment_dto import (
    ApprovalRoleAssignmentView,
    TargetMembershipInfo,
)
from flowpilot.modules.approval.domain.enums import ApprovalRoleKey
from flowpilot.modules.approval.domain.models import ApprovalRoleAssignment
from flowpilot.modules.audit.application.ports import AuditWriterPort


class ApprovalRoleAssignmentListQuery(Protocol):
    """Tenant'ın AKTİF rol atamalarını (email ile) deterministik sırada listeler."""

    def list_assignments(self, *, tenant_id: UUID) -> list[ApprovalRoleAssignmentView]: ...


class ApprovalRoleAssignmentManagementRepository(Protocol):
    """Rol atama yazma/okuma (aynı transaction; advisory lock + FOR UPDATE + CAS)."""

    def acquire_role_lock(self, *, tenant_id: UUID, role_key: ApprovalRoleKey) -> None:
        """Tenant+role advisory xact lock: aynı role eşzamanlı atamaları serileştirir."""
        ...

    def find_active_for_update(
        self, *, tenant_id: UUID, role_key: ApprovalRoleKey
    ) -> ApprovalRoleAssignment | None:
        """Rol'ün aktif atamasını satır kilidiyle (FOR UPDATE) okur; yoksa None."""
        ...

    def revoke_checked(
        self, assignment: ApprovalRoleAssignment, *, expected_version: int, now: datetime
    ) -> None:
        """Aktif atamayı optimistic CAS ile revoked yapar (version+1); stale → concurrency."""
        ...

    def insert_active(self, assignment: ApprovalRoleAssignment) -> None:
        """Yeni aktif atama satırı ekler (partial-unique ihlali → concurrency)."""
        ...


class TargetMembershipReader(Protocol):
    """Cross-module READ: hedef kullanıcının tenant içindeki üyelik durumu + email.

    None → üye değil (404); status != active → atanamaz (409). Yalnız email_snapshot döner.
    """

    def find(self, *, tenant_id: UUID, user_id: UUID) -> TargetMembershipInfo | None: ...


class ApprovalRoleAssignmentUpdateUnitOfWork(Protocol):
    """Tek transaction: rol atama yönetimi + hedef üyelik + audit (wiring'de compose)."""

    assignments: ApprovalRoleAssignmentManagementRepository
    target_memberships: TargetMembershipReader
    audit: AuditWriterPort

    def __enter__(self) -> ApprovalRoleAssignmentUpdateUnitOfWork: ...

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
