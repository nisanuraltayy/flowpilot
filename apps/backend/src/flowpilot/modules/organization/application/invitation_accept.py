"""Davet önizleme + kabul use-case'leri (FP-E03-001, Dilim B).

Kabul yetkisi capability (token) + authenticated actor + e-posta eşleşmesidir; merkezi
owner/admin permission'ına TABİ DEĞİLDİR. Kabul + üyelik oluşturma + (varsa) idempotency
kaydı + audit AYNI transaction'da yazılır (yarım state bırakılmaz). Ham token log/audit/
exception'a ve idempotency alanlarına GİRMEZ.

Idempotency-Key (opsiyonel):
- Yoksa: tek-kullanımlık davet state'i doğal idempotency anchor'ıdır.
- Varsa: aynı actor + org + aynı payload replay → önceki sonuç (duplicate=true);
  aynı key farklı payload/org → 409, hiçbir state değişmeden.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
    IdempotencyKeyReuseError,
    InvitationAcceptedByOtherError,
    InvitationConcurrencyError,
    InvitationEmailMismatchError,
    InvitationEmailMissingError,
    InvitationExpiredError,
    InvitationNotFoundError,
    MembershipInactiveConflictError,
)
from flowpilot.modules.organization.application.invitation_ports import (
    AcceptIdempotencyRecord,
    InvitationAcceptUnitOfWork,
    InvitationPreviewQuery,
)
from flowpilot.modules.organization.domain.invitation import Invitation, InvitationStatus
from flowpilot.modules.organization.domain.invitation_token import (
    hash_invitation_token,
    invitation_accept_fingerprint,
)
from flowpilot.modules.organization.domain.membership import Membership, MembershipStatus
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


@dataclass(frozen=True)
class _AcceptPlan:
    """Kabul kararının planı: yeni üyelik mi, mevcut aktif üyelik mi (rol korunur)."""

    create_membership: bool
    membership_id: UUID
    role: str
    duplicate: bool


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
    """Davet kabulü: tek kullanımlık, e-posta eşleşmeli, atomik membership + idempotency."""

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
        org = command.organization_id
        key = command.idempotency_key
        fingerprint = (
            invitation_accept_fingerprint(organization_id=str(org), token_hash=token_hash)
            if key is not None
            else None
        )

        with self._uow_factory() as uow:
            uow.set_actor_context(actor_id)
            uow.set_tenant_context(org)

            # 0) Idempotency ön-kontrol: aynı key kaydı varsa replay/409 (state'e dokunmadan).
            if key is not None:
                existing = uow.idempotency.find_for_actor(
                    actor_user_id=actor_id, idempotency_key=key
                )
                if existing is not None:
                    decision = self._idempotency_decision(
                        existing, org=org, fingerprint=fingerprint
                    )
                    uow.rollback()
                    return decision

            invitation = uow.invitations.find_by_token_hash(tenant_id=org, token_hash=token_hash)
            if invitation is None or invitation.status is InvitationStatus.REVOKED:
                raise InvitationNotFoundError("davet bulunamadı")  # 404

            if invitation.status is InvitationStatus.ACCEPTED:
                result = self._resolve_accepted_replay(uow, invitation, actor_id)
                uow.rollback()
                return result

            if _is_effectively_expired(invitation, now):
                raise InvitationExpiredError("davet süresi dolmuş")  # 410

            snapshot = self._email_reader.find_email_snapshot(UserId(actor_id))
            normalized = snapshot.strip().lower() if snapshot else ""
            if not normalized:
                raise InvitationEmailMissingError("actor e-postası yok")  # 403
            if normalized != invitation.invited_email:
                raise InvitationEmailMismatchError("e-posta eşleşmiyor")  # 403

            plan = self._plan(uow, invitation=invitation, org=org, actor_id=actor_id)

            # invitation CAS: eşzamanlı iki kabuldan yalnız biri geçer.
            accepted = invitation.accept(accepted_by=UserId(actor_id), now=now)
            try:
                uow.invitations.update_checked(accepted, expected_version=invitation.version)
            except InvitationConcurrencyError:
                reread = uow.invitations.find_by_token_hash(tenant_id=org, token_hash=token_hash)
                if reread is None:
                    raise
                result = self._resolve_accepted_replay(uow, reread, actor_id)
                uow.rollback()
                return result

            # Idempotency kaydı, ÜYELİK'ten ÖNCE: aynı-key yarışında tek kazanan + kaybeden
            # membership'e hiç dokunmadan çözülür (409 veya replay).
            if key is not None and fingerprint is not None:
                inserted = uow.idempotency.add_if_absent(
                    AcceptIdempotencyRecord(
                        tenant_id=org,
                        actor_user_id=actor_id,
                        idempotency_key=key,
                        request_fingerprint=fingerprint,
                        invitation_id=invitation.id.value,
                        membership_id=plan.membership_id,
                        response_role=plan.role,
                        response_status=MembershipStatus.ACTIVE.value,
                        response_duplicate=plan.duplicate,
                    ),
                    record_id=self._ids.new_uuid(),
                    now=now,
                )
                if not inserted:
                    existing = uow.idempotency.find_for_actor(
                        actor_user_id=actor_id, idempotency_key=key
                    )
                    uow.rollback()
                    if existing is None:
                        raise IdempotencyKeyReuseError("idempotency çakışması")
                    return self._idempotency_decision(existing, org=org, fingerprint=fingerprint)

            membership: Membership | None = None
            if plan.create_membership:
                membership = Membership.create_active(
                    id=MembershipId(plan.membership_id),
                    tenant_id=TenantId(org),
                    user_id=UserId(actor_id),
                    role=invitation.role,
                    created_at=now,
                )
                uow.memberships.add(membership)
            # Audit sırası: invitation.accepted → (yeni üye ise) membership.joined.
            self._audit_accepted(
                uow,
                invitation=accepted,
                actor_id=actor_id,
                membership_id=plan.membership_id,
                membership_role=plan.role,
                already_member=not plan.create_membership,
            )
            if membership is not None:
                self._audit_joined(uow, membership=membership, actor_id=actor_id)
            uow.commit()

        return AcceptInvitationResult(
            organization_id=org,
            membership_id=plan.membership_id,
            role=plan.role,
            status=MembershipStatus.ACTIVE.value,
            duplicate=plan.duplicate,
        )

    # --- yardımcılar ---------------------------------------------------------

    def _plan(
        self,
        uow: InvitationAcceptUnitOfWork,
        *,
        invitation: Invitation,
        org: UUID,
        actor_id: UUID,
    ) -> _AcceptPlan:
        existing = uow.memberships.find_by_user(tenant_id=org, user_id=actor_id)
        if existing is None:
            return _AcceptPlan(
                create_membership=True,
                membership_id=self._ids.new_uuid(),
                role=invitation.role.value,
                duplicate=False,
            )
        if existing.status != MembershipStatus.ACTIVE.value:
            raise MembershipInactiveConflictError("mevcut üyelik aktif değil")  # 409
        # Zaten aktif üye: rolü DEĞİŞTİRME; daveti kapat, mevcut rolü koru.
        return _AcceptPlan(
            create_membership=False,
            membership_id=existing.membership_id,
            role=existing.role,
            duplicate=True,
        )

    def _idempotency_decision(
        self, record: AcceptIdempotencyRecord, *, org: UUID, fingerprint: str | None
    ) -> AcceptInvitationResult:
        # Aynı org + aynı fingerprint → replay (duplicate). Farklı org/payload → 409.
        if record.tenant_id != org or record.request_fingerprint != fingerprint:
            raise IdempotencyKeyReuseError("aynı Idempotency-Key farklı payload/org ile kullanıldı")
        return AcceptInvitationResult(
            organization_id=record.tenant_id,
            membership_id=record.membership_id,
            role=record.response_role,
            status=record.response_status,
            duplicate=True,
        )

    def _resolve_accepted_replay(
        self, uow: InvitationAcceptUnitOfWork, invitation: Invitation, actor_id: UUID
    ) -> AcceptInvitationResult:
        accepted_by = invitation.accepted_by_user_id
        if accepted_by is None or accepted_by.value != actor_id:
            raise InvitationAcceptedByOtherError("davet başka kullanıcıya ait")
        membership = uow.memberships.find_by_user(
            tenant_id=invitation.tenant_id.value, user_id=actor_id
        )
        if membership is None:
            raise InvitationAcceptedByOtherError("davet çözümlenemedi")
        return AcceptInvitationResult(
            organization_id=invitation.tenant_id.value,
            membership_id=membership.membership_id,
            role=membership.role,
            status=membership.status,
            duplicate=True,
        )

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
