"""Üye yönetimi application port'ları (aggregate-specific; generic repository YASAK).

`MemberUpdateUnitOfWork` tek transaction'da membership yönetimi + approval sorumluluk
kontrolü + audit'i birleştirir (compose; wiring'de kurulur). `approval_responsibility`
cross-module bir READ contract'tır — organization, approval/workflow infrastructure'ını
DOĞRUDAN import etmez; sorgu composition root'ta wire edilir.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

from flowpilot.modules.audit.application.ports import AuditWriterPort
from flowpilot.modules.organization.application.member_dto import MemberView
from flowpilot.modules.organization.domain.membership import Membership


class MemberListQuery(Protocol):
    """Tenant üyelerini (email ile) listeleyen salt-okunur read model (tenant-scoped, RLS)."""

    def list_members(self, *, tenant_id: UUID, limit: int) -> list[MemberView]: ...


class MembershipManagementRepository(Protocol):
    """Üye yönetimi yazma/okuma (aynı transaction; FOR UPDATE kilitleme + optimistic CAS)."""

    def acquire_tenant_lock(self, *, tenant_id: UUID) -> None:
        """Tenant-scoped transaction advisory lock: üye güncellemelerini tenant içinde
        serileştirir. Owner-invariant yarışında tutarlı kilit sırası sağlar → mutual
        owner-demotion deadlock'unu önler (FOR UPDATE tek başına yeterli sıralama vermez)."""
        ...

    def find_by_user_for_update(self, *, tenant_id: UUID, user_id: UUID) -> Membership | None:
        """Hedef üyeliği satır kilidiyle (FOR UPDATE) okur; yoksa None."""
        ...

    def count_active_owners_for_update(self, *, tenant_id: UUID) -> int:
        """Aktif owner üyelik satırlarını FOR UPDATE kilitler ve sayar (final-owner invariant)."""
        ...

    def update_checked(self, membership: Membership, *, expected_version: int) -> None:
        """Optimistic CAS ile günceller (version+1, updated_at); stale → concurrency hatası."""
        ...


class ApprovalResponsibilityQuery(Protocol):
    """Cross-module READ: kullanıcının aktif onay sorumluluğu var mı? (suspend/remove guard).

    Aktif approval_role_assignment VEYA pending/active workflow approval task = sorumluluk.
    """

    def has_active_responsibilities(self, *, tenant_id: UUID, user_id: UUID) -> bool: ...


class MemberUpdateUnitOfWork(Protocol):
    """Tek transaction: membership yönetimi + approval sorumluluk + audit (wiring'de compose)."""

    memberships: MembershipManagementRepository
    approval_responsibility: ApprovalResponsibilityQuery
    audit: AuditWriterPort

    def __enter__(self) -> MemberUpdateUnitOfWork: ...

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
