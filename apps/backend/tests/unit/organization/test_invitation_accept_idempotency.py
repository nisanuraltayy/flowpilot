"""Davet kabul Idempotency-Key birim testleri (fake adapter'larla)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from flowpilot.modules.organization.application.invitation_accept import AcceptInvitationHandler
from flowpilot.modules.organization.application.invitation_dto import AcceptInvitationCommand
from flowpilot.modules.organization.application.invitation_errors import IdempotencyKeyReuseError
from flowpilot.modules.organization.application.invitation_ports import (
    AcceptIdempotencyRecord,
    MembershipRecord,
)
from flowpilot.modules.organization.domain.invitation import Invitation, InvitationStatus
from flowpilot.modules.organization.domain.invitation_token import (
    hash_invitation_token,
    invitation_accept_fingerprint,
)
from flowpilot.modules.organization.domain.membership import MembershipRole
from flowpilot.shared.identifiers import InvitationId, TenantId, UserId
from tests.unit.fakes import FakeClock, FakeIdGenerator
from tests.unit.organization.invitation_fakes import (
    FakeAcceptIdempotencyRepository,
    FakeActorEmailReader,
    FakeAuditWriter,
    FakeInvitationAcceptUnitOfWork,
    FakeInvitationRepository,
    FakeMembershipWriteRepository,
)

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
TENANT = uuid4()
OTHER_TENANT = uuid4()
ACTOR = uuid4()
EMAIL = "invitee@example.com"
RAW_TOKEN = "raw-accept-token"
KEY = "idem-key-1"
FINGERPRINT = invitation_accept_fingerprint(
    organization_id=str(TENANT), token_hash=hash_invitation_token(RAW_TOKEN)
)


def _pending() -> Invitation:
    return Invitation.create(
        id=InvitationId(uuid4()),
        tenant_id=TenantId(TENANT),
        invited_email=EMAIL,
        role=MembershipRole.MEMBER,
        token_hash=hash_invitation_token(RAW_TOKEN),
        invited_by_user_id=UserId(uuid4()),
        created_at=_NOW,
    )


def _handler(
    *,
    invitations: FakeInvitationRepository,
    idempotency: FakeAcceptIdempotencyRepository | None = None,
    memberships: FakeMembershipWriteRepository | None = None,
    audit: FakeAuditWriter | None = None,
) -> tuple[AcceptInvitationHandler, FakeInvitationAcceptUnitOfWork]:
    uow = FakeInvitationAcceptUnitOfWork(
        invitations,
        memberships or FakeMembershipWriteRepository(),
        audit or FakeAuditWriter(),
        idempotency or FakeAcceptIdempotencyRepository(),
    )
    handler = AcceptInvitationHandler(
        unit_of_work_factory=lambda: uow,
        email_reader=FakeActorEmailReader({ACTOR: EMAIL}),
        clock=FakeClock(_NOW),
        id_generator=FakeIdGenerator([uuid4() for _ in range(10)]),
    )
    return handler, uow


def _command(
    *, key: str | None = KEY, org: object = TENANT, token: str = RAW_TOKEN
) -> AcceptInvitationCommand:
    return AcceptInvitationCommand(
        organization_id=org,  # type: ignore[arg-type]
        actor_user_id=ACTOR,
        raw_token=token,
        idempotency_key=key,
    )


def _seed_record(
    *, membership_id: object = None, fingerprint: str = FINGERPRINT, tenant: object = TENANT
) -> AcceptIdempotencyRecord:
    return AcceptIdempotencyRecord(
        tenant_id=tenant,  # type: ignore[arg-type]
        actor_user_id=ACTOR,
        idempotency_key=KEY,
        request_fingerprint=fingerprint,
        invitation_id=uuid4(),
        membership_id=membership_id or uuid4(),  # type: ignore[arg-type]
        response_role="member",
        response_status="active",
        response_duplicate=False,
    )


def test_first_accept_with_key_records_idempotency() -> None:
    repo = FakeInvitationRepository(seed=[_pending()])
    idem = FakeAcceptIdempotencyRepository()
    handler, _uow = _handler(invitations=repo, idempotency=idem)
    result = handler.handle(_command())
    assert result.duplicate is False and result.role == "member"
    assert len(idem.records) == 1
    assert idem.records[0].idempotency_key == KEY
    assert idem.records[0].request_fingerprint == FINGERPRINT
    # Ham token idempotency alanlarında yok.
    assert RAW_TOKEN not in str(idem.records[0])


def test_same_key_same_payload_replays_stored_snapshot() -> None:
    membership_id = uuid4()
    idem = FakeAcceptIdempotencyRepository([_seed_record(membership_id=membership_id)])
    repo = FakeInvitationRepository(seed=[_pending()])
    audit = FakeAuditWriter()
    handler, uow = _handler(invitations=repo, idempotency=idem, audit=audit)
    result = handler.handle(_command())
    assert result.duplicate is True
    assert result.membership_id == membership_id
    assert result.role == "member" and result.status == "active"
    assert uow.committed == 0  # replay yeni yazım yok
    assert uow.memberships.added == []
    assert audit.records == []  # replay yeni audit üretmez
    assert len(idem.records) == 1  # yeni idempotency kaydı yok


def test_same_key_different_token_conflicts() -> None:
    idem = FakeAcceptIdempotencyRepository([_seed_record()])
    repo = FakeInvitationRepository(seed=[_pending()])
    handler, uow = _handler(invitations=repo, idempotency=idem)
    with pytest.raises(IdempotencyKeyReuseError):
        handler.handle(_command(token="a-different-token"))
    assert uow.committed == 0
    assert uow.memberships.added == []


def test_same_key_different_org_conflicts() -> None:
    # Kayıt TENANT'ta; farklı org (OTHER_TENANT) ile aynı key → 409 (actor-scoped find).
    idem = FakeAcceptIdempotencyRepository([_seed_record(tenant=TENANT)])
    repo = FakeInvitationRepository(seed=[_pending()])
    handler, uow = _handler(invitations=repo, idempotency=idem)
    with pytest.raises(IdempotencyKeyReuseError):
        handler.handle(_command(org=OTHER_TENANT))
    assert uow.committed == 0


def test_different_key_same_payload_natural_replay() -> None:
    # İlk kabul (key K1) daveti accepted yaptı; farklı key (K2) → doğal davet-state replay.
    accepted = replace(
        _pending(), status=InvitationStatus.ACCEPTED, accepted_by_user_id=UserId(ACTOR)
    )
    memberships = FakeMembershipWriteRepository(
        {(TENANT, ACTOR): MembershipRecord(membership_id=uuid4(), role="member", status="active")}
    )
    repo = FakeInvitationRepository(seed=[accepted])
    handler, uow = _handler(invitations=repo, memberships=memberships)
    result = handler.handle(_command(key="a-second-key"))
    assert result.duplicate is True  # davet state anchor'ı
    assert uow.committed == 0


def test_no_header_preserves_natural_idempotency() -> None:
    accepted = replace(
        _pending(), status=InvitationStatus.ACCEPTED, accepted_by_user_id=UserId(ACTOR)
    )
    memberships = FakeMembershipWriteRepository(
        {(TENANT, ACTOR): MembershipRecord(membership_id=uuid4(), role="member", status="active")}
    )
    repo = FakeInvitationRepository(seed=[accepted])
    handler, uow = _handler(invitations=repo, memberships=memberships)
    result = handler.handle(_command(key=None))  # header yok
    assert result.duplicate is True
    assert len(uow.idempotency.records) == 0  # header yoksa idempotency kaydı yok
