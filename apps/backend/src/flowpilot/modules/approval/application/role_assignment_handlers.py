"""Approval rol atama listeleme + değiştirme use-case'leri (FP-E10-004).

Business logic BURADA. owner/admin gerçek AKTİF üyelere approval role_key atayabilir.
Yetki merkezi authorization boundary'sindedir (route'ta dağınık rol kontrolü YOK). Atama
değişikliği tek transaction'da: eski aktif atama revoked, yeni aktif atama oluşturulur,
audit yazılır. Tenant+role advisory lock + FOR UPDATE + optimistic CAS ile eşzamanlı
atamada yalnız biri kazanır. No-op (aynı kullanıcı) idempotenttir (yazım/audit YOK).

Mevcut workflow task'ları DEĞİŞTİRMEZ — task'lar oluşturuldukları anki assignee'ye
pinlenmiştir; yalnız SONRAKİ satın alma talepleri yeni atamayı kullanır.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from flowpilot.modules.approval.application.role_assignment_dto import (
    ApprovalRoleAssignmentView,
    AssignApprovalRoleCommand,
    AssignApprovalRoleResult,
)
from flowpilot.modules.approval.application.role_assignment_errors import (
    ApprovalRoleActorNotMemberError,
    ApprovalRoleAssignmentConcurrencyError,
    ApprovalRoleExpectedVersionRequiredError,
    ApprovalRoleTargetNotActiveError,
    ApprovalRoleTargetNotFoundError,
    InvalidApprovalRoleKeyError,
)
from flowpilot.modules.approval.application.role_assignment_ports import (
    ApprovalRoleAssignmentListQuery,
    ApprovalRoleAssignmentUpdateUnitOfWork,
)
from flowpilot.modules.approval.domain.enums import ApprovalRoleKey
from flowpilot.modules.approval.domain.models import (
    ApprovalRoleAssignment,
    ApprovalRoleAssignmentId,
)
from flowpilot.modules.audit.application.dto import AuditEventType, AuditRecord
from flowpilot.modules.authorization.application.access import Permission, ensure_permitted
from flowpilot.modules.organization.application.contracts import MembershipQuery
from flowpilot.shared.clock import ClockPort
from flowpilot.shared.identifiers import TenantId, UserId
from flowpilot.shared.ids import IdGeneratorPort

UpdateUnitOfWorkFactory = Callable[[], ApprovalRoleAssignmentUpdateUnitOfWork]

_AGGREGATE = "approval_role_assignment"
_ACTIVE = "active"


def _parse_role_key(raw: str) -> ApprovalRoleKey:
    try:
        return ApprovalRoleKey(raw)
    except ValueError as exc:
        raise InvalidApprovalRoleKeyError(f"geçersiz role_key: {raw!r}") from exc


class ListApprovalRoleAssignmentsHandler:
    """Aktif approval rol atamalarını listeler (owner/admin; member → 403; non-member → 404)."""

    def __init__(
        self, *, list_query: ApprovalRoleAssignmentListQuery, membership_query: MembershipQuery
    ) -> None:
        self._query = list_query
        self._memberships = membership_query

    def handle(self, *, tenant_id: UUID, actor_user_id: UUID) -> list[ApprovalRoleAssignmentView]:
        actor = self._memberships.find_active(tenant_id=tenant_id, user_id=actor_user_id)
        if actor is None:
            raise ApprovalRoleActorNotMemberError("aktif üyelik bulunamadı")
        ensure_permitted(role=actor.role, permission=Permission.APPROVAL_ROLE_ASSIGNMENT_READ)
        return self._query.list_assignments(tenant_id=tenant_id)


class AssignApprovalRoleHandler:
    """Bir approval role_key'i gerçek bir aktif üyeye atar (atomik, invariant-korumalı)."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UpdateUnitOfWorkFactory,
        membership_query: MembershipQuery,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._memberships = membership_query
        self._clock = clock
        self._ids = id_generator

    def handle(self, command: AssignApprovalRoleCommand) -> AssignApprovalRoleResult:
        # 1) role_key doğrulaması (422).
        role_key = _parse_role_key(command.role_key)

        # 2) Coarse authz: actor aktif üye + owner/admin (RLS'li kendi session'ı).
        actor = self._memberships.find_active(
            tenant_id=command.tenant_id, user_id=command.actor_user_id
        )
        if actor is None:
            raise ApprovalRoleActorNotMemberError("aktif üyelik bulunamadı")
        ensure_permitted(role=actor.role, permission=Permission.APPROVAL_ROLE_ASSIGNMENT_CHANGE)

        now = self._clock.now()
        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)
            # Tenant+role serileştirme: eşzamanlı aynı-rol atamada yalnız biri kazanır.
            uow.assignments.acquire_role_lock(tenant_id=command.tenant_id, role_key=role_key)

            # 3) Hedef aktif üyelik doğrulama (404 non-member, 409 not-active).
            target = uow.target_memberships.find(
                tenant_id=command.tenant_id, user_id=command.target_user_id
            )
            if target is None:
                raise ApprovalRoleTargetNotFoundError("hedef kullanıcı bu organizasyonda üye değil")
            if target.status != _ACTIVE:
                raise ApprovalRoleTargetNotActiveError("hedef üyelik aktif değil — atanamaz")

            # 4) Mevcut aktif atamayı kilitle.
            current = uow.assignments.find_active_for_update(
                tenant_id=command.tenant_id, role_key=role_key
            )

            if current is not None:
                # 5) expected_version zorunlu ve eşleşmeli.
                if command.expected_version is None:
                    raise ApprovalRoleExpectedVersionRequiredError(
                        "mevcut atama var; expected_version gerekli"
                    )
                if current.version != command.expected_version:
                    raise ApprovalRoleAssignmentConcurrencyError("stale expected_version")
                # 6) No-op: aynı kullanıcı → idempotent duplicate (yazım/audit YOK).
                if current.assigned_user_id.value == command.target_user_id:
                    uow.rollback()
                    return self._snapshot(current, target.email, duplicate=True)
                # 7) Eski aktif atamayı revoked yap (CAS), yeni aktif atama oluştur.
                next_version = current.version + 1
                uow.assignments.revoke_checked(
                    current, expected_version=command.expected_version, now=now
                )
                new_assignment = self._new_active(command, role_key, now, version=next_version)
                uow.assignments.insert_active(new_assignment)
                self._write_audit(uow, command.actor_user_id, previous=current, new=new_assignment)
            else:
                # Aktif atama yok → create (expected_version opsiyonel, göz ardı edilir).
                new_assignment = self._new_active(command, role_key, now, version=1)
                uow.assignments.insert_active(new_assignment)
                self._write_audit(uow, command.actor_user_id, previous=None, new=new_assignment)

            uow.commit()

        return self._snapshot(new_assignment, target.email, duplicate=False)

    def _new_active(
        self,
        command: AssignApprovalRoleCommand,
        role_key: ApprovalRoleKey,
        now: object,
        *,
        version: int,
    ) -> ApprovalRoleAssignment:
        return ApprovalRoleAssignment.create_active(
            id=ApprovalRoleAssignmentId(self._ids.new_uuid()),
            tenant_id=TenantId(command.tenant_id),
            role_key=role_key,
            assigned_user_id=UserId(command.target_user_id),
            created_at=now,  # type: ignore[arg-type]
            version=version,
        )

    def _snapshot(
        self, assignment: ApprovalRoleAssignment, email: str | None, *, duplicate: bool
    ) -> AssignApprovalRoleResult:
        return AssignApprovalRoleResult(
            assignment_id=assignment.id.value,
            role_key=assignment.role_key.value,
            assigned_user_id=assignment.assigned_user_id.value,
            assigned_user_email=email,
            status=assignment.status.value,
            version=assignment.version,
            duplicate=duplicate,
        )

    def _write_audit(
        self,
        uow: ApprovalRoleAssignmentUpdateUnitOfWork,
        actor_user_id: UUID,
        *,
        previous: ApprovalRoleAssignment | None,
        new: ApprovalRoleAssignment,
    ) -> None:
        metadata: dict[str, str | int] = {
            "role_key": new.role_key.value,
            "new_assignment_id": str(new.id.value),
            "new_user_id": str(new.assigned_user_id.value),
            "actor_user_id": str(actor_user_id),
            "new_version": new.version,
            "previous_assignment_id": str(previous.id.value) if previous else "",
            "previous_user_id": str(previous.assigned_user_id.value) if previous else "",
            "previous_version": previous.version if previous else 0,
        }
        uow.audit.append(
            AuditRecord(
                event_id=self._ids.new_uuid(),
                tenant_id=new.tenant_id.value,
                aggregate_type=_AGGREGATE,
                aggregate_id=new.id.value,
                event_type=AuditEventType.APPROVAL_ROLE_ASSIGNMENT_CHANGED,
                occurred_at=new.updated_at,
                actor_user_id=actor_user_id,
                role_key=new.role_key.value,
                metadata=metadata,
            )
        )
