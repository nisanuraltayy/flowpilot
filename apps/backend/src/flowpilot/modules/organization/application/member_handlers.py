"""Üye listeleme + güncelleme use-case'leri (FP-E03-002).

Business logic BURADA. Yetki iki katmanlı: (1) merkezi coarse permission (owner/admin
yönetebilir, member yasak), (2) hedefe göre domain policy (admin yalnız member; owner-only
owner yönetimi). Son aktif owner invariant'ı FOR UPDATE kilidiyle korunur. Suspend/remove,
aktif onay sorumluluğu olan kullanıcıyı engeller. Değişiklik + audit AYNI transaction'da;
optimistic CAS ile stale write 409. No-op idempotenttir (yeni yazım/audit YOK).
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from flowpilot.modules.audit.application.dto import AuditEventType, AuditRecord
from flowpilot.modules.authorization.application.access import Permission, ensure_permitted
from flowpilot.modules.organization.application.contracts import MembershipQuery
from flowpilot.modules.organization.application.member_dto import (
    MemberView,
    UpdateMemberCommand,
    UpdateMemberResult,
)
from flowpilot.modules.organization.application.member_errors import (
    ApprovalResponsibilityConflictError,
    FinalOwnerError,
    InvalidMemberUpdateError,
    MemberActorNotMemberError,
    MemberNotFoundError,
    MemberSelfMutationError,
    MembershipConcurrencyError,
)
from flowpilot.modules.organization.application.member_ports import (
    MemberListQuery,
    MemberUpdateUnitOfWork,
)
from flowpilot.modules.organization.domain.member_management_policy import (
    authorize_member_change,
)
from flowpilot.modules.organization.domain.membership import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from flowpilot.shared.clock import ClockPort
from flowpilot.shared.ids import IdGeneratorPort

MemberUpdateUnitOfWorkFactory = Callable[[], MemberUpdateUnitOfWork]

_AGGREGATE = "organization_membership"
# Yalnız bu status değerleri istekle set edilebilir (invited hariç — yeni üyelikte kullanılmaz).
_SETTABLE_STATUSES = {
    MembershipStatus.ACTIVE,
    MembershipStatus.SUSPENDED,
    MembershipStatus.REMOVED,
}
_STATUS_PERMISSION = {
    MembershipStatus.SUSPENDED: Permission.ORGANIZATION_MEMBER_SUSPEND,
    MembershipStatus.ACTIVE: Permission.ORGANIZATION_MEMBER_REACTIVATE,
    MembershipStatus.REMOVED: Permission.ORGANIZATION_MEMBER_REMOVE,
}
_STATUS_EVENT = {
    MembershipStatus.SUSPENDED: AuditEventType.ORGANIZATION_MEMBERSHIP_SUSPENDED,
    MembershipStatus.ACTIVE: AuditEventType.ORGANIZATION_MEMBERSHIP_REACTIVATED,
    MembershipStatus.REMOVED: AuditEventType.ORGANIZATION_MEMBERSHIP_REMOVED,
}


def _parse_role(raw: str | None) -> MembershipRole | None:
    if raw is None:
        return None
    try:
        return MembershipRole(raw)
    except ValueError as exc:
        raise InvalidMemberUpdateError(f"geçersiz rol: {raw!r}") from exc


def _parse_status(raw: str | None) -> MembershipStatus | None:
    if raw is None:
        return None
    try:
        status = MembershipStatus(raw)
    except ValueError as exc:
        raise InvalidMemberUpdateError(f"geçersiz status: {raw!r}") from exc
    if status not in _SETTABLE_STATUSES:
        raise InvalidMemberUpdateError(f"bu status set edilemez: {raw!r}")
    return status


class ListOrganizationMembersHandler:
    """Tenant üyelerini listeler (owner/admin; member → 403; non-member → 404)."""

    def __init__(
        self, *, member_list_query: MemberListQuery, membership_query: MembershipQuery
    ) -> None:
        self._query = member_list_query
        self._memberships = membership_query

    def handle(self, *, tenant_id: UUID, actor_user_id: UUID, limit: int) -> list[MemberView]:
        actor = self._memberships.find_active(tenant_id=tenant_id, user_id=actor_user_id)
        if actor is None:
            raise MemberActorNotMemberError("aktif üyelik bulunamadı")
        ensure_permitted(role=actor.role, permission=Permission.ORGANIZATION_MEMBER_READ)
        return self._query.list_members(tenant_id=tenant_id, limit=limit)


class UpdateOrganizationMemberHandler:
    """Üye rol/status güncelleme use-case'i (atomik, invariant-korumalı)."""

    def __init__(
        self,
        *,
        unit_of_work_factory: MemberUpdateUnitOfWorkFactory,
        membership_query: MembershipQuery,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._memberships = membership_query
        self._clock = clock
        self._ids = id_generator

    def handle(self, command: UpdateMemberCommand) -> UpdateMemberResult:
        # 1) Girdi doğrulaması (422): en az biri, geçerli değerler.
        new_role = _parse_role(command.new_role)
        new_status = _parse_status(command.new_status)
        if new_role is None and new_status is None:
            raise InvalidMemberUpdateError("role veya status'tan en az biri gerekli")

        # 2) Coarse authz: actor aktif üye + owner/admin (RLS'li kendi session'ı).
        actor = self._memberships.find_active(
            tenant_id=command.tenant_id, user_id=command.actor_user_id
        )
        if actor is None:
            raise MemberActorNotMemberError("aktif üyelik bulunamadı")
        self._ensure_coarse_permissions(actor.role, new_role=new_role, new_status=new_status)

        now = self._clock.now()
        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)
            # Tenant-scoped serileştirme: mutual owner-demotion deadlock'unu önler ve
            # final-owner invariant'ını yarışa karşı korur (FOR UPDATE ile birlikte).
            uow.memberships.acquire_tenant_lock(tenant_id=command.tenant_id)

            target = uow.memberships.find_by_user_for_update(
                tenant_id=command.tenant_id, user_id=command.target_user_id
            )
            if target is None:
                raise MemberNotFoundError("hedef üyelik bulunamadı")

            # 3) Self-mutation yasağı (409).
            if target.user_id.value == command.actor_user_id:
                raise MemberSelfMutationError("kullanıcı kendi üyeliğini değiştiremez")

            # 4) Hedefe göre ince yetki (403): admin yalnız member; owner rolü admin veremez.
            authorize_member_change(
                actor_role=actor.role, target_role=target.role, new_role=new_role
            )

            # 5) Stale version (409) — no-op'tan önce.
            if target.version != command.expected_version:
                raise MembershipConcurrencyError("stale expected_version")

            # 6) No-op → idempotent duplicate (yeni yazım/audit yok).
            if target.is_noop(new_role=new_role, new_status=new_status):
                uow.rollback()
                return self._snapshot(target, duplicate=True)

            # 7) Son aktif owner invariant'ı (owner'ı deaktive eden değişiklikte, FOR UPDATE).
            #    count_active_owners_for_update SADECE gerektiğinde çağrılır (owner satırlarını
            #    kilitler); short-circuit ile gereksiz kilit alınmaz.
            if (
                target.deactivates_owner(new_role=new_role, new_status=new_status)
                and uow.memberships.count_active_owners_for_update(tenant_id=command.tenant_id) <= 1
            ):
                raise FinalOwnerError("son aktif owner korunur")

            # 8) Suspend/remove → aktif onay sorumluluğu guard'ı (409).
            if new_status in (
                MembershipStatus.SUSPENDED,
                MembershipStatus.REMOVED,
            ) and uow.approval_responsibility.has_active_responsibilities(
                tenant_id=command.tenant_id, user_id=command.target_user_id
            ):
                raise ApprovalResponsibilityConflictError(
                    "önce kullanıcının aktif onay sorumlulukları yeniden atanmalıdır"
                )

            # 9) Domain geçişini uygula (removed-terminal / invalid-transition → 409).
            updated = target.apply_management_change(
                new_role=new_role, new_status=new_status, now=now
            )
            # 10) Optimistic CAS (stale → MembershipConcurrencyError).
            uow.memberships.update_checked(updated, expected_version=command.expected_version)
            # 11) Audit (role_changed ve/veya status event), AYNI transaction.
            self._write_audit(
                uow, actor_user_id=command.actor_user_id, before=target, after=updated
            )
            uow.commit()

        return self._snapshot(updated, duplicate=False, version=command.expected_version + 1)

    def _ensure_coarse_permissions(
        self,
        actor_role: str,
        *,
        new_role: MembershipRole | None,
        new_status: MembershipStatus | None,
    ) -> None:
        if new_role is not None:
            ensure_permitted(role=actor_role, permission=Permission.ORGANIZATION_MEMBER_ROLE_CHANGE)
        if new_status is not None:
            ensure_permitted(role=actor_role, permission=_STATUS_PERMISSION[new_status])

    def _snapshot(
        self, membership: Membership, *, duplicate: bool, version: int | None = None
    ) -> UpdateMemberResult:
        return UpdateMemberResult(
            membership_id=membership.id.value,
            user_id=membership.user_id.value,
            role=membership.role.value,
            status=membership.status.value,
            version=version if version is not None else membership.version,
            duplicate=duplicate,
        )

    def _write_audit(
        self,
        uow: MemberUpdateUnitOfWork,
        *,
        actor_user_id: UUID,
        before: Membership,
        after: Membership,
    ) -> None:
        new_version = before.version + 1

        def record(event: AuditEventType) -> AuditRecord:
            return AuditRecord(
                event_id=self._ids.new_uuid(),
                tenant_id=after.tenant_id.value,
                aggregate_type=_AGGREGATE,
                aggregate_id=after.id.value,
                event_type=event,
                occurred_at=after.updated_at,
                actor_user_id=actor_user_id,
                role_key=after.role.value,
                metadata={
                    "target_user_id": str(after.user_id.value),
                    "membership_id": str(after.id.value),
                    "previous_role": before.role.value,
                    "new_role": after.role.value,
                    "previous_status": before.status.value,
                    "new_status": after.status.value,
                    "version": new_version,
                },
            )

        if after.role is not before.role:
            uow.audit.append(record(AuditEventType.ORGANIZATION_MEMBERSHIP_ROLE_CHANGED))
        if after.status is not before.status:
            uow.audit.append(record(_STATUS_EVENT[after.status]))
