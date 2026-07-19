"""EnsureDefaultApprovalRoleAssignments + DefaultApproverResolver (owner kararı #4).

Organizasyonun approval rolleri yoksa, ilk onay akışı kullanılmadan önce ÜÇ rol de
aktif owner kullanıcısına idempotent atanır. Public role-management endpoint'i DEĞİL.
Tekrar çalıştırıldığında duplicate üretmez; mevcut açık atamaları OVERWRITE ETMEZ;
aktif owner yoksa kontrollü configuration error üretir. organization infrastructure
tablolarına DOĞRUDAN erişmez (MembershipQuery contract'ı üzerinden).
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from flowpilot.modules.approval.application.errors import ActiveOwnerNotFoundError
from flowpilot.modules.approval.application.ports import (
    ApprovalAssignmentUnitOfWork,
    ApprovalRoleAssignmentQuery,
)
from flowpilot.modules.approval.domain.enums import ALL_ROLE_KEYS
from flowpilot.modules.approval.domain.models import (
    ApprovalRoleAssignment,
    ApprovalRoleAssignmentId,
)
from flowpilot.modules.organization.application.contracts import MembershipQuery
from flowpilot.shared.clock import ClockPort
from flowpilot.shared.identifiers import TenantId, UserId
from flowpilot.shared.ids import IdGeneratorPort

AssignmentUnitOfWorkFactory = Callable[[], ApprovalAssignmentUnitOfWork]


class EnsureDefaultApprovalRoleAssignments:
    """Eksik approval rollerini aktif owner'a idempotent atar."""

    def __init__(
        self,
        *,
        unit_of_work_factory: AssignmentUnitOfWorkFactory,
        membership_query: MembershipQuery,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._memberships = membership_query
        self._clock = clock
        self._ids = id_generator

    def handle(self, *, tenant_id: TenantId, actor_user_id: UUID | None = None) -> None:
        owner = self._memberships.find_active_owner(tenant_id=tenant_id.value)
        if owner is None:
            raise ActiveOwnerNotFoundError("aktif owner bulunamadı — varsayılan onaycı atanamaz")
        owner_id = UserId(owner.user_id)
        now = self._clock.now()
        with self._uow_factory() as uow:
            if actor_user_id is not None:
                uow.set_actor_context(actor_user_id)
            uow.set_tenant_context(tenant_id.value)
            for role_key in ALL_ROLE_KEYS:
                assignment = ApprovalRoleAssignment.create_active(
                    id=ApprovalRoleAssignmentId(self._ids.new_uuid()),
                    tenant_id=tenant_id,
                    role_key=role_key,
                    assigned_user_id=owner_id,
                    created_at=now,
                )
                # ON CONFLICT DO NOTHING → mevcut aktif atama OVERWRITE edilmez.
                uow.approval_role_assignments.add_if_absent(assignment)
            uow.commit()


class DefaultApproverResolver:
    """`RoleAssigneeResolver` — eksikleri ensure eder, sonra aktif eşlemeyi döndürür."""

    def __init__(
        self,
        *,
        ensure: EnsureDefaultApprovalRoleAssignments,
        assignment_query: ApprovalRoleAssignmentQuery,
    ) -> None:
        self._ensure = ensure
        self._query = assignment_query

    def resolve_all(self, *, tenant_id: UUID, actor_user_id: UUID) -> dict[str, str]:
        self._ensure.handle(tenant_id=TenantId(tenant_id), actor_user_id=actor_user_id)
        return {role: str(uid) for role, uid in self._query.active_map(tenant_id=tenant_id).items()}
