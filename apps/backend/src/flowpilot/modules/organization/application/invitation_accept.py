"""Davet önizleme + kabul use-case'leri (FP-E03-001, Dilim B).

Kabul yetkisi capability (token) + authenticated actor + e-posta eşleşmesidir; merkezi
owner/admin permission'ına TABİ DEĞİLDİR. Kabul + üyelik oluşturma + audit AYNI
transaction'da yazılır (yarım state bırakılmaz). Ham token log/audit/exception'a girmez.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from flowpilot.modules.audit.application.dto import AuditEventType, AuditRecord
from flowpilot.modules.identity.application.contracts import ActorEmailReader
from flowpilot.modules.organization.application.invitation_dto import (
    AcceptInvitationCommand,
    AcceptInvitationResult,
    PreviewInvitationResult,
)
from flowpilot.modules.organization.application.invitation_errors import (
    InvitationAcceptedByOtherError,
    InvitationConcurrencyError,
    InvitationEmailMismatchError,
    InvitationEmailMissingError,
    InvitationExpiredError,
    InvitationNotFoundError,
    MembershipInactiveConflictError,
)
from flowpilot.modules.organization.application.invitation_ports import (
    InvitationAcceptUnitOfWork,
    InvitationPreviewQuery,
    MembershipRecord,
)
from flowpilot.modules.organization.domain.invitation import Invitation, InvitationStatus
from flowpilot.modules.organization.domain.invitation_token import hash_invitation_token
from flowpilot.modules.organization.domain.membership import (
    Membership,
    MembershipStatus,
)
from flowpilot.shared.clock import ClockPort
from flowpilot.shared.identifiers import MembershipId, TenantId, UserId
from flowpilot.shared.ids import IdGeneratorPort

AcceptUnitOfWorkFactory = Callable[[], InvitationAcceptUnitOfWork]

_INVITATION_AGGREGATE = "organization_invitation"
_MEMBERSHIP_AGGREGATE = "organization_membership"


def _is_effectively_expired(invitation: Invitation, now: datetime) -> bool:
    return invitation.status is InvitationStatus.EXPIRED or (
        invitation.status is InvitationStatus.PENDING and invitation.is_expired(now)
    )


class PreviewInvitationHandler:
    """Auth'suz davet önizlemesi (minimal, güvenli). Token/e-posta döndürmez, audit yazmaz."""

    def __init__(self, *, preview_query: InvitationPreviewQuery, clock: ClockPort) -> None:
        self._query = preview_query
        self._clock = clock

    def handle(self, *, organization_id: UUID, raw_token: str) -> PreviewInvitationResult:
        token_hash = hash_invitation_token(raw_token)
        row = self._query.find(tenant_id=organization_id, token_hash=token_hash)
        # Bilinmeyen token / yanlış tenant (RLS) / revoked → 404 (varlık sızdırmaz).
        if row is None or row.status == InvitationStatus.REVOKED.value:
            raise InvitationNotFoundError("davet bulunamadı")
        now = self._clock.now()
        expired = row.status == InvitationStatus.EXPIRED.value or (
            row.status == InvitationStatus.PENDING.value and now >= row.expires_at
        )
        if expired:
            raise InvitationExpiredError("davet süresi dolmuş")
        # pending (geçerli) veya accepted → güvenli önizleme (token holder'a durum gösterilir).
        return PreviewInvitationResult(
            organization_id=row.organization_id,
            organization_name=row.organization_name,
            role=row.role,
            status=row.status,
            expires_at=row.expires_at,
        )


class AcceptInvitationHandler:
    """Davet kabulü: tek kullanımlık, e-posta eşleşmeli, atomik membership + audit."""

    def __init__(
        self,
        *,
        unit_of_work_factory: AcceptUnitOfWorkFactory,
        email_reader: ActorEmailReader,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._email_reader = email_reader
        self._clock = clock
        self._ids = id_generator

    def handle(self, command: AcceptInvitationCommand) -> AcceptInvitationResult:
        token_hash = hash_invitation_token(command.raw_token)
        now = self._clock.now()
        actor_id = command.actor_user_id

        with self._uow_factory() as uow:
            uow.set_actor_context(actor_id)
            uow.set_tenant_context(command.organization_id)

            invitation = uow.invitations.find_by_token_hash(
                tenant_id=command.organization_id, token_hash=token_hash
            )
            if invitation is None or invitation.status is InvitationStatus.REVOKED:
                raise InvitationNotFoundError(
                    "davet bulunamadı"
                )  # 404 (unknown/revoked/cross-tenant)

            if invitation.status is InvitationStatus.ACCEPTED:
                # Replay: yalnız kabul eden aynı actor idempotent başarı alır; diğer → 404.
                result = self._resolve_accepted_replay(uow, invitation, actor_id)
                uow.rollback()  # replay yeni yazım/audit üretmez
                return result

            if _is_effectively_expired(invitation, now):
                raise InvitationExpiredError("davet süresi dolmuş")  # 410

            # E-posta eşleşmesi: email_snapshot yoksa 403; normalize (trim+lower) eşleşmezse 403.
            snapshot = self._email_reader.find_email_snapshot(UserId(actor_id))
            normalized = snapshot.strip().lower() if snapshot else ""
            if not normalized:
                raise InvitationEmailMissingError("actor e-postası yok")  # 403
            if normalized != invitation.invited_email:
                raise InvitationEmailMismatchError("e-posta eşleşmiyor")  # 403

            existing = uow.memberships.find_by_user(
                tenant_id=command.organization_id, user_id=actor_id
            )
            if existing is not None:
                return self._accept_with_existing_membership(
                    uow, invitation=invitation, actor_id=actor_id, existing=existing, now=now
                )
            return self._accept_new_member(
                uow,
                invitation=invitation,
                actor_id=actor_id,
                token_hash=token_hash,
                now=now,
            )

    # --- yollar --------------------------------------------------------------

    def _accept_new_member(
        self,
        uow: InvitationAcceptUnitOfWork,
        *,
        invitation: Invitation,
        actor_id: UUID,
        token_hash: str,
        now: datetime,
    ) -> AcceptInvitationResult:
        accepted = invitation.accept(accepted_by=UserId(actor_id), now=now)
        # CAS ÖNCE: eşzamanlı iki kabuldan yalnız biri geçer. Kaybeden → replay çözümü.
        try:
            uow.invitations.update_checked(accepted, expected_version=invitation.version)
        except InvitationConcurrencyError:
            reread = uow.invitations.find_by_token_hash(
                tenant_id=invitation.tenant_id.value, token_hash=token_hash
            )
            if reread is None:
                raise
            result = self._resolve_accepted_replay(uow, reread, actor_id)
            uow.rollback()
            return result

        membership = Membership.create_active(
            id=MembershipId(self._ids.new_uuid()),
            tenant_id=TenantId(invitation.tenant_id.value),
            user_id=UserId(actor_id),
            role=invitation.role,
            created_at=now,
        )
        uow.memberships.add(membership)  # unique(tenant_id,user_id) — yalnız kazanan ekler
        self._audit_accepted(
            uow,
            invitation=accepted,
            actor_id=actor_id,
            membership_id=membership.id.value,
            membership_role=invitation.role.value,
            already_member=False,
        )
        self._audit_joined(uow, membership=membership, actor_id=actor_id)
        uow.commit()
        return AcceptInvitationResult(
            organization_id=invitation.tenant_id.value,
            membership_id=membership.id.value,
            role=invitation.role.value,
            status=MembershipStatus.ACTIVE.value,
            duplicate=False,
        )

    def _accept_with_existing_membership(
        self,
        uow: InvitationAcceptUnitOfWork,
        *,
        invitation: Invitation,
        actor_id: UUID,
        existing: MembershipRecord,
        now: datetime,
    ) -> AcceptInvitationResult:
        # Suspended/removed (veya active olmayan) → otomatik reaktive YOK → 409.
        if existing.status != MembershipStatus.ACTIVE.value:
            raise MembershipInactiveConflictError("mevcut üyelik aktif değil")
        # Zaten aktif üye: daveti kapat (accepted), ROLÜ DEĞİŞTİRME, yeni membership YOK.
        accepted = invitation.accept(accepted_by=UserId(actor_id), now=now)
        uow.invitations.update_checked(accepted, expected_version=invitation.version)
        self._audit_accepted(
            uow,
            invitation=accepted,
            actor_id=actor_id,
            membership_id=existing.membership_id,
            membership_role=existing.role,
            already_member=True,
        )
        uow.commit()
        return AcceptInvitationResult(
            organization_id=invitation.tenant_id.value,
            membership_id=existing.membership_id,
            role=existing.role,  # mevcut rol KORUNUR (davet rolüne yükseltilmez)
            status=MembershipStatus.ACTIVE.value,
            duplicate=True,
        )

    def _resolve_accepted_replay(
        self, uow: InvitationAcceptUnitOfWork, invitation: Invitation, actor_id: UUID
    ) -> AcceptInvitationResult:
        # Yalnız daveti KABUL EDEN aynı actor idempotent başarı alır; başkası → 404.
        accepted_by = invitation.accepted_by_user_id
        if accepted_by is None or accepted_by.value != actor_id:
            raise InvitationAcceptedByOtherError("davet başka kullanıcıya ait")
        membership = uow.memberships.find_by_user(
            tenant_id=invitation.tenant_id.value, user_id=actor_id
        )
        if membership is None:
            # Kabul eden actor'ın üyeliği bulunamadı (beklenmez) → sızdırmayan 404.
            raise InvitationAcceptedByOtherError("davet çözümlenemedi")
        return AcceptInvitationResult(
            organization_id=invitation.tenant_id.value,
            membership_id=membership.membership_id,
            role=membership.role,
            status=membership.status,
            duplicate=True,
        )

    # --- audit ---------------------------------------------------------------

    def _audit_accepted(
        self,
        uow: InvitationAcceptUnitOfWork,
        *,
        invitation: Invitation,
        actor_id: UUID,
        membership_id: UUID,
        membership_role: str,
        already_member: bool,
    ) -> None:
        uow.audit.append(
            AuditRecord(
                event_id=self._ids.new_uuid(),
                tenant_id=invitation.tenant_id.value,
                aggregate_type=_INVITATION_AGGREGATE,
                aggregate_id=invitation.id.value,
                event_type=AuditEventType.ORGANIZATION_INVITATION_ACCEPTED,
                occurred_at=invitation.updated_at,
                actor_user_id=actor_id,
                role_key=invitation.role.value,
                metadata={
                    "invitation_id": str(invitation.id.value),
                    "membership_id": str(membership_id),
                    "invited_role": invitation.role.value,
                    "membership_role": membership_role,
                    "already_member": "true" if already_member else "false",
                },
            )
        )

    def _audit_joined(
        self, uow: InvitationAcceptUnitOfWork, *, membership: Membership, actor_id: UUID
    ) -> None:
        uow.audit.append(
            AuditRecord(
                event_id=self._ids.new_uuid(),
                tenant_id=membership.tenant_id.value,
                aggregate_type=_MEMBERSHIP_AGGREGATE,
                aggregate_id=membership.id.value,
                event_type=AuditEventType.ORGANIZATION_MEMBERSHIP_JOINED,
                occurred_at=membership.created_at,
                actor_user_id=actor_id,
                role_key=membership.role.value,
                metadata={
                    "membership_id": str(membership.id.value),
                    "role": membership.role.value,
                },
            )
        )
