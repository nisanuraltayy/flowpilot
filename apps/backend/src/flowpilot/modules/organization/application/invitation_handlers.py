"""Invitation use-case handler'ları: Create / ListPending / Revoke (FP-E03-001).

Business logic BURADA (endpoint/repository/SQLAlchemy'ye gömülmez). Yetki merkezi
authorization boundary'sinden sorulur (dağınık rol kontrolü YOK). Davet oluşturma ve
iptali audit ile AYNI transaction'da yazılır (SPK-11); ham token audit'e/log'a girmez.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from flowpilot.modules.audit.application.dto import AuditEventType, AuditRecord
from flowpilot.modules.authorization.application.access import Permission, ensure_permitted
from flowpilot.modules.identity.application.contracts import UserEmailLookup
from flowpilot.modules.organization.application.contracts import MembershipQuery
from flowpilot.modules.organization.application.invitation_dto import (
    CreateInvitationCommand,
    CreateInvitationResult,
    PendingInvitationView,
    RevokeInvitationCommand,
    RevokeInvitationResult,
)
from flowpilot.modules.organization.application.invitation_errors import (
    AlreadyActiveMemberError,
    DuplicatePendingInvitationError,
    IdempotencyKeyReuseError,
    InvitationActorNotMemberError,
    InvitationNotFoundError,
)
from flowpilot.modules.organization.application.invitation_ports import (
    InvitationAcceptUrlBuilder,
    InvitationQuery,
    InvitationUnitOfWork,
)
from flowpilot.modules.organization.domain.invitation import (
    Invitation,
    InvitationStatus,
    invitation_role_from,
    normalize_invited_email,
)
from flowpilot.modules.organization.domain.invitation_token import (
    InvitationTokenGeneratorPort,
    hash_invitation_token,
    invitation_request_fingerprint,
)
from flowpilot.shared.clock import ClockPort
from flowpilot.shared.identifiers import InvitationId, TenantId, UserId
from flowpilot.shared.ids import IdGeneratorPort

InvitationUnitOfWorkFactory = Callable[[], InvitationUnitOfWork]

_AGGREGATE_TYPE = "organization_invitation"


def _require_management_role(
    membership_query: MembershipQuery,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    permission: Permission,
) -> str:
    """Actor aktif üye mi + permission var mı? (merkezi authorization).

    Aktif üye değil → `InvitationActorNotMemberError` (404). Üye ama yetkisiz →
    `PermissionDeniedError` (403). Döndürdüğü değer actor'ın membership rolüdür.
    """
    membership = membership_query.find_active(tenant_id=tenant_id, user_id=actor_user_id)
    if membership is None:
        raise InvitationActorNotMemberError("aktif üyelik bulunamadı")
    ensure_permitted(role=membership.role, permission=permission)
    return membership.role


class CreateInvitationHandler:
    """Davet oluşturma use-case'i (owner/admin; token hash'lenir, audit AYNI tx)."""

    def __init__(
        self,
        *,
        unit_of_work_factory: InvitationUnitOfWorkFactory,
        membership_query: MembershipQuery,
        email_lookup: UserEmailLookup,
        token_generator: InvitationTokenGeneratorPort,
        accept_url_builder: InvitationAcceptUrlBuilder,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._memberships = membership_query
        self._email_lookup = email_lookup
        self._tokens = token_generator
        self._accept_url = accept_url_builder
        self._clock = clock
        self._ids = id_generator

    def handle(self, command: CreateInvitationCommand) -> CreateInvitationResult:
        # 1) Yetki ÖNCE: aktif owner/admin mi? (merkezi authorization; RLS'li kendi
        # session'ı). Non-member → 404, member-ama-yetkisiz → 403. Yetkisiz actor'a
        # girdi doğrulama sonucu (422) sızdırmamak için authz doğrulamadan ÖNCE gelir.
        _require_management_role(
            self._memberships,
            tenant_id=command.tenant_id,
            actor_user_id=command.actor_user_id,
            permission=Permission.ORGANIZATION_INVITATION_CREATE,
        )

        # 2) Domain girdi doğrulaması (DB'ye dokunmadan → 422).
        email = normalize_invited_email(command.invited_email)
        role = invitation_role_from(command.role)

        fingerprint = invitation_request_fingerprint(invited_email=email, role=role.value)
        now = self._clock.now()

        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)

            # 3) Idempotency-Key replay: aynı key → aynı sonuç (duplicate, token'sız).
            if command.idempotency_key:
                stored = uow.invitations.find_by_idempotency_key(
                    tenant_id=command.tenant_id, idempotency_key=command.idempotency_key
                )
                if stored is not None:
                    if stored.request_fingerprint != fingerprint:
                        raise IdempotencyKeyReuseError("ayni key farkli payload ile kullanildi")
                    uow.rollback()
                    return self._duplicate_result(stored.invitation)

            # 4) Zaten aktif üye olan e-posta için davet oluşturulmaz (→ 409).
            if self._email_matches_active_member(command.tenant_id, email):
                raise AlreadyActiveMemberError("e-posta zaten aktif üye")

            # 5) Aktif bekleyen davet var mı? (ön-kontrol; DB partial unique backstop).
            existing = uow.invitations.find_active_pending_by_email(
                tenant_id=command.tenant_id, invited_email=email, now=now
            )
            if existing is not None:
                raise DuplicatePendingInvitationError("bu e-posta için zaten bekleyen davet var")

            # 6) Güvenli token üret → yalnız hash sakla.
            raw_token = self._tokens.new_raw_token()
            token_hash = hash_invitation_token(raw_token)
            invitation = Invitation.create(
                id=InvitationId(self._ids.new_uuid()),
                tenant_id=TenantId(command.tenant_id),
                invited_email=email,
                role=role,
                token_hash=token_hash,
                invited_by_user_id=UserId(command.actor_user_id),
                created_at=now,
            )
            uow.invitations.add(
                invitation,
                idempotency_key=command.idempotency_key,
                request_fingerprint=fingerprint,
            )
            self._append_audit(
                uow,
                event_type=AuditEventType.ORGANIZATION_INVITATION_CREATED,
                invitation=invitation,
                actor_user_id=command.actor_user_id,
            )
            uow.commit()

        accept_url = self._accept_url.build(tenant_id=command.tenant_id, raw_token=raw_token)
        return CreateInvitationResult(
            invitation_id=invitation.id.value,
            invited_email=invitation.invited_email,
            role=invitation.role.value,
            status=invitation.status.value,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
            raw_token=raw_token,
            accept_url=accept_url,
            duplicate=False,
        )

    def _email_matches_active_member(self, tenant_id: UUID, email: str) -> bool:
        # identity_users GLOBAL; e-posta ile kullanıcı ID'leri bulunur, sonra YALNIZ bu
        # tenant'ta aktif membership kontrol edilir (cross-tenant sızma yok).
        for user_id in self._email_lookup.find_user_ids_by_email(email):
            if self._memberships.find_active(tenant_id=tenant_id, user_id=user_id) is not None:
                return True
        return False

    @staticmethod
    def _duplicate_result(invitation: Invitation) -> CreateInvitationResult:
        # Idempotent replay: token/accept_url YOK (ham token yalnız ilk üretimde döner).
        return CreateInvitationResult(
            invitation_id=invitation.id.value,
            invited_email=invitation.invited_email,
            role=invitation.role.value,
            status=invitation.status.value,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
            raw_token=None,
            accept_url=None,
            duplicate=True,
        )

    def _append_audit(
        self,
        uow: InvitationUnitOfWork,
        *,
        event_type: AuditEventType,
        invitation: Invitation,
        actor_user_id: UUID,
    ) -> None:
        # metadata güvenli, sınırlı bağlam taşır (invited_email + rol); TOKEN ASLA.
        uow.audit.append(
            AuditRecord(
                event_id=self._ids.new_uuid(),
                tenant_id=invitation.tenant_id.value,
                aggregate_type=_AGGREGATE_TYPE,
                aggregate_id=invitation.id.value,
                event_type=event_type,
                occurred_at=invitation.updated_at,
                actor_user_id=actor_user_id,
                role_key=invitation.role.value,
                metadata={"invited_email": invitation.invited_email, "role": invitation.role.value},
            )
        )


class ListPendingInvitationsHandler:
    """Bekleyen (pending + süresi dolmamış) davetleri listeler (owner/admin, tenant-scoped)."""

    def __init__(
        self,
        *,
        invitation_query: InvitationQuery,
        membership_query: MembershipQuery,
        clock: ClockPort,
    ) -> None:
        self._query = invitation_query
        self._memberships = membership_query
        self._clock = clock

    def handle(
        self, *, tenant_id: UUID, actor_user_id: UUID, limit: int
    ) -> list[PendingInvitationView]:
        _require_management_role(
            self._memberships,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            permission=Permission.ORGANIZATION_INVITATION_READ,
        )
        return self._query.list_pending(tenant_id=tenant_id, now=self._clock.now(), limit=limit)


class RevokeInvitationHandler:
    """Bekleyen daveti iptal eder (owner/admin). Idempotent; audit AYNI tx."""

    def __init__(
        self,
        *,
        unit_of_work_factory: InvitationUnitOfWorkFactory,
        membership_query: MembershipQuery,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._memberships = membership_query
        self._clock = clock
        self._ids = id_generator

    def handle(self, command: RevokeInvitationCommand) -> RevokeInvitationResult:
        _require_management_role(
            self._memberships,
            tenant_id=command.tenant_id,
            actor_user_id=command.actor_user_id,
            permission=Permission.ORGANIZATION_INVITATION_REVOKE,
        )
        now = self._clock.now()
        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)

            invitation = uow.invitations.find_by_id(
                tenant_id=command.tenant_id, invitation_id=command.invitation_id
            )
            if invitation is None:
                raise InvitationNotFoundError("davet bulunamadı")

            # Idempotent: zaten revoked → yeni yazım YOK, audit YOK.
            if invitation.status is InvitationStatus.REVOKED:
                uow.rollback()
                return RevokeInvitationResult(
                    invitation_id=invitation.id.value,
                    status=invitation.status.value,
                    duplicate=True,
                )

            revoked = invitation.revoke(now=now)  # accepted → InvitationNotRevocableError (409)
            uow.invitations.update_checked(revoked, expected_version=invitation.version)
            self._append_revoke_audit(uow, invitation=revoked, actor_user_id=command.actor_user_id)
            uow.commit()

        return RevokeInvitationResult(
            invitation_id=revoked.id.value, status=revoked.status.value, duplicate=False
        )

    def _append_revoke_audit(
        self, uow: InvitationUnitOfWork, *, invitation: Invitation, actor_user_id: UUID
    ) -> None:
        uow.audit.append(
            AuditRecord(
                event_id=self._ids.new_uuid(),
                tenant_id=invitation.tenant_id.value,
                aggregate_type=_AGGREGATE_TYPE,
                aggregate_id=invitation.id.value,
                event_type=AuditEventType.ORGANIZATION_INVITATION_REVOKED,
                occurred_at=invitation.updated_at,
                actor_user_id=actor_user_id,
                role_key=invitation.role.value,
                metadata={"invited_email": invitation.invited_email, "role": invitation.role.value},
            )
        )
