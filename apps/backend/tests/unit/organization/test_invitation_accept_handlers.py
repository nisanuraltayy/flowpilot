"""Preview + Accept use-case birim testleri (fake adapter'larla)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from flowpilot.modules.organization.application.invitation_accept import (
    AcceptInvitationHandler,
    PreviewInvitationHandler,
)
from flowpilot.modules.organization.application.invitation_dto import AcceptInvitationCommand
from flowpilot.modules.organization.application.invitation_errors import (
    InvitationAcceptedByOtherError,
    InvitationEmailMismatchError,
    InvitationEmailMissingError,
    InvitationExpiredError,
    InvitationNotFoundError,
    MembershipInactiveConflictError,
)
from flowpilot.modules.organization.application.invitation_ports import (
    InvitationPreviewRow,
    MembershipRecord,
)
from flowpilot.modules.organization.domain.invitation import Invitation, InvitationStatus
from flowpilot.modules.organization.domain.invitation_token import hash_invitation_token
from flowpilot.modules.organization.domain.membership import MembershipRole
from flowpilot.shared.identifiers import InvitationId, TenantId, UserId
from tests.unit.fakes import FakeClock, FakeIdGenerator
from tests.unit.organization.invitation_fakes import (
    FakeActorEmailReader,
    FakeAuditWriter,
    FakeInvitationAcceptUnitOfWork,
    FakeInvitationPreviewQuery,
    FakeInvitationRepository,
    FakeMembershipWriteRepository,
)

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
TENANT = uuid4()
OTHER_TENANT = uuid4()
ACTOR = uuid4()
INVITER = uuid4()
INVITED_EMAIL = "invitee@example.com"
RAW_TOKEN = "raw-accept-token"
TOKEN_HASH = hash_invitation_token(RAW_TOKEN)


def _invitation(
    *,
    tenant: object = TENANT,
    email: str = INVITED_EMAIL,
    role: MembershipRole = MembershipRole.MEMBER,
    status: InvitationStatus = InvitationStatus.PENDING,
    created_at: datetime = _NOW,
    accepted_by: object = None,
    token: str = RAW_TOKEN,
) -> Invitation:
    from dataclasses import replace

    base = Invitation.create(
        id=InvitationId(uuid4()),
        tenant_id=TenantId(tenant),  # type: ignore[arg-type]
        invited_email=email,
        role=role,
        token_hash=hash_invitation_token(token),
        invited_by_user_id=UserId(INVITER),
        created_at=created_at,
    )
    if status is not InvitationStatus.PENDING or accepted_by is not None:
        base = replace(
            base,
            status=status,
            accepted_by_user_id=UserId(accepted_by) if accepted_by else None,  # type: ignore[arg-type]
        )
    return base


# ============================ PREVIEW =======================================


def _preview_handler(row: InvitationPreviewRow | None) -> PreviewInvitationHandler:
    rows = {(TENANT, TOKEN_HASH): row} if row is not None else {}
    return PreviewInvitationHandler(
        preview_query=FakeInvitationPreviewQuery(rows), clock=FakeClock(_NOW)
    )


def _preview_row(*, status: str, expires_at: datetime) -> InvitationPreviewRow:
    return InvitationPreviewRow(
        organization_id=TENANT,
        organization_name="Acme",
        role="member",
        status=status,
        expires_at=expires_at,
    )


def test_preview_pending_valid() -> None:
    handler = _preview_handler(_preview_row(status="pending", expires_at=_NOW + timedelta(days=7)))
    result = handler.handle(organization_id=TENANT, raw_token=RAW_TOKEN)
    assert result.organization_name == "Acme"
    assert result.role == "member"
    assert result.status == "pending"


def test_preview_accepted_shows_status() -> None:
    handler = _preview_handler(_preview_row(status="accepted", expires_at=_NOW + timedelta(days=1)))
    result = handler.handle(organization_id=TENANT, raw_token=RAW_TOKEN)
    assert result.status == "accepted"


def test_preview_unknown_token_not_found() -> None:
    handler = _preview_handler(None)
    with pytest.raises(InvitationNotFoundError):
        handler.handle(organization_id=TENANT, raw_token=RAW_TOKEN)


def test_preview_revoked_not_found() -> None:
    handler = _preview_handler(_preview_row(status="revoked", expires_at=_NOW + timedelta(days=1)))
    with pytest.raises(InvitationNotFoundError):
        handler.handle(organization_id=TENANT, raw_token=RAW_TOKEN)


def test_preview_expired_status_gone() -> None:
    handler = _preview_handler(_preview_row(status="expired", expires_at=_NOW - timedelta(days=1)))
    with pytest.raises(InvitationExpiredError):
        handler.handle(organization_id=TENANT, raw_token=RAW_TOKEN)


def test_preview_pending_past_expiry_gone() -> None:
    handler = _preview_handler(
        _preview_row(status="pending", expires_at=_NOW - timedelta(minutes=1))
    )
    with pytest.raises(InvitationExpiredError):
        handler.handle(organization_id=TENANT, raw_token=RAW_TOKEN)


# ============================ ACCEPT ========================================


def _accept_handler(
    *,
    invitations: FakeInvitationRepository,
    memberships: FakeMembershipWriteRepository | None = None,
    email: str | None = INVITED_EMAIL,
    audit: FakeAuditWriter | None = None,
) -> tuple[AcceptInvitationHandler, FakeInvitationAcceptUnitOfWork]:
    uow = FakeInvitationAcceptUnitOfWork(
        invitations, memberships or FakeMembershipWriteRepository(), audit or FakeAuditWriter()
    )
    handler = AcceptInvitationHandler(
        unit_of_work_factory=lambda: uow,
        email_reader=FakeActorEmailReader({ACTOR: email}),
        clock=FakeClock(_NOW),
        id_generator=FakeIdGenerator([uuid4() for _ in range(5)]),
    )
    return handler, uow


def _command(*, tenant: object = TENANT, token: str = RAW_TOKEN) -> AcceptInvitationCommand:
    return AcceptInvitationCommand(
        organization_id=tenant,  # type: ignore[arg-type]
        actor_user_id=ACTOR,
        raw_token=token,
    )


@pytest.mark.parametrize("role", [MembershipRole.ADMIN, MembershipRole.MEMBER])
def test_correct_email_creates_active_membership(role: MembershipRole) -> None:
    repo = FakeInvitationRepository(seed=[_invitation(role=role)])
    handler, uow = _accept_handler(invitations=repo)
    result = handler.handle(_command())

    assert result.duplicate is False
    assert result.role == role.value
    assert result.status == "active"
    assert uow.committed == 1
    assert len(uow.memberships.added) == 1
    assert uow.memberships.added[0].role is role
    # Davet accepted + accepted_by pinlendi.
    assert repo.saved[0].status is InvitationStatus.ACCEPTED
    assert repo.saved[0].accepted_by_user_id == UserId(ACTOR)
    # Audit: accepted + membership.joined.
    events = [r.event_type.value for r in uow.audit.records]
    assert events == ["organization.invitation.accepted", "organization.membership.joined"]


def test_wrong_email_forbidden() -> None:
    repo = FakeInvitationRepository(seed=[_invitation()])
    handler, uow = _accept_handler(invitations=repo, email="someone.else@example.com")
    with pytest.raises(InvitationEmailMismatchError):
        handler.handle(_command())
    assert uow.committed == 0
    assert uow.memberships.added == []
    assert repo.saved[0].status is InvitationStatus.PENDING  # kabul edilmedi


def test_missing_email_snapshot_forbidden() -> None:
    repo = FakeInvitationRepository(seed=[_invitation()])
    handler, uow = _accept_handler(invitations=repo, email=None)
    with pytest.raises(InvitationEmailMissingError):
        handler.handle(_command())
    assert uow.committed == 0


def test_email_match_is_case_insensitive_and_trimmed() -> None:
    repo = FakeInvitationRepository(seed=[_invitation()])
    handler, _ = _accept_handler(invitations=repo, email=f"  {INVITED_EMAIL.upper()} ")
    result = handler.handle(_command())
    assert result.duplicate is False


def test_expired_invitation_gone() -> None:
    repo = FakeInvitationRepository(
        seed=[_invitation(created_at=_NOW - timedelta(days=8))]  # expires geçmişte
    )
    handler, uow = _accept_handler(invitations=repo)
    with pytest.raises(InvitationExpiredError):
        handler.handle(_command())
    assert uow.committed == 0


def test_revoked_invitation_not_found() -> None:
    repo = FakeInvitationRepository(seed=[_invitation(status=InvitationStatus.REVOKED)])
    handler, _ = _accept_handler(invitations=repo)
    with pytest.raises(InvitationNotFoundError):
        handler.handle(_command())


def test_cross_tenant_token_not_found() -> None:
    # Davet OTHER_TENANT'ta; TENANT context'inde token bulunamaz.
    repo = FakeInvitationRepository(seed=[_invitation(tenant=OTHER_TENANT)])
    handler, _ = _accept_handler(invitations=repo)
    with pytest.raises(InvitationNotFoundError):
        handler.handle(_command(tenant=TENANT))


def test_same_user_replay_is_duplicate() -> None:
    memberships = FakeMembershipWriteRepository(
        {(TENANT, ACTOR): MembershipRecord(membership_id=uuid4(), role="member", status="active")}
    )
    repo = FakeInvitationRepository(
        seed=[_invitation(status=InvitationStatus.ACCEPTED, accepted_by=ACTOR)]
    )
    handler, uow = _accept_handler(invitations=repo, memberships=memberships)
    result = handler.handle(_command())
    assert result.duplicate is True
    assert result.role == "member"
    assert uow.committed == 0  # replay yeni yazım yok
    assert uow.audit.records == []


def test_accepted_by_other_user_not_found() -> None:
    repo = FakeInvitationRepository(
        seed=[_invitation(status=InvitationStatus.ACCEPTED, accepted_by=uuid4())]
    )
    handler, _ = _accept_handler(invitations=repo)
    with pytest.raises(InvitationAcceptedByOtherError):
        handler.handle(_command())


def test_existing_active_membership_kept_role_not_upgraded() -> None:
    existing_id = uuid4()
    memberships = FakeMembershipWriteRepository(
        {
            (TENANT, ACTOR): MembershipRecord(
                membership_id=existing_id, role="member", status="active"
            )
        }
    )
    # Davet ADMIN rolü taşıyor ama mevcut member rolü YÜKSELTİLMEZ.
    repo = FakeInvitationRepository(seed=[_invitation(role=MembershipRole.ADMIN)])
    handler, uow = _accept_handler(invitations=repo, memberships=memberships)
    result = handler.handle(_command())
    assert result.duplicate is True
    assert result.role == "member"  # korunur
    assert result.membership_id == existing_id
    assert uow.memberships.added == []  # yeni membership yok
    assert repo.saved[0].status is InvitationStatus.ACCEPTED  # davet kapatıldı
    events = [r.event_type.value for r in uow.audit.records]
    assert events == ["organization.invitation.accepted"]  # joined YOK


@pytest.mark.parametrize("bad_status", ["suspended", "removed"])
def test_suspended_or_removed_membership_conflicts(bad_status: str) -> None:
    memberships = FakeMembershipWriteRepository(
        {(TENANT, ACTOR): MembershipRecord(membership_id=uuid4(), role="member", status=bad_status)}
    )
    repo = FakeInvitationRepository(seed=[_invitation()])
    handler, uow = _accept_handler(invitations=repo, memberships=memberships)
    with pytest.raises(MembershipInactiveConflictError):
        handler.handle(_command())
    assert uow.committed == 0
    assert repo.saved[0].status is InvitationStatus.PENDING  # reaktive edilmedi
