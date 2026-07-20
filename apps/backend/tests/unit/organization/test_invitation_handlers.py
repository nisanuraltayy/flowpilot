"""Invitation use-case handler birim testleri (fake adapter'larla)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from flowpilot.modules.authorization.application.access import PermissionDeniedError
from flowpilot.modules.organization.application.invitation_dto import (
    CreateInvitationCommand,
    PendingInvitationView,
    RevokeInvitationCommand,
)
from flowpilot.modules.organization.application.invitation_errors import (
    AlreadyActiveMemberError,
    DuplicatePendingInvitationError,
    IdempotencyKeyReuseError,
    InvalidInvitedEmailError,
    InvitationActorNotMemberError,
    InvitationNotFoundError,
    InvitationNotRevocableError,
    InvitationRoleNotAllowedError,
)
from flowpilot.modules.organization.application.invitation_handlers import (
    CreateInvitationHandler,
    ListPendingInvitationsHandler,
    RevokeInvitationHandler,
)
from flowpilot.modules.organization.domain.invitation import (
    Invitation,
    InvitationStatus,
)
from flowpilot.modules.organization.domain.invitation_token import hash_invitation_token
from flowpilot.modules.organization.domain.membership import MembershipRole
from flowpilot.shared.identifiers import InvitationId, TenantId, UserId
from tests.unit.fakes import FakeClock, FakeIdGenerator
from tests.unit.organization.invitation_fakes import (
    FakeAcceptUrlBuilder,
    FakeAuditWriter,
    FakeEmailLookup,
    FakeInvitationQuery,
    FakeInvitationRepository,
    FakeInvitationUnitOfWork,
    FakeMembershipQuery,
)

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
TENANT = uuid4()
OTHER_TENANT = uuid4()
OWNER = uuid4()
ADMIN = uuid4()
MEMBER = uuid4()
STRANGER = uuid4()


def _memberships() -> FakeMembershipQuery:
    return FakeMembershipQuery(
        {
            (TENANT, OWNER): "owner",
            (TENANT, ADMIN): "admin",
            (TENANT, MEMBER): "member",
        }
    )


def _build_create(
    *,
    repository: FakeInvitationRepository | None = None,
    audit: FakeAuditWriter | None = None,
    memberships: FakeMembershipQuery | None = None,
    email_lookup: FakeEmailLookup | None = None,
    tokens: list[str] | None = None,
    ids: list[str] | None = None,
) -> tuple[CreateInvitationHandler, FakeInvitationUnitOfWork]:
    repo = repository or FakeInvitationRepository()
    uow = FakeInvitationUnitOfWork(repo, audit or FakeAuditWriter())
    id_values = [uuid4() for _ in range(10)] if ids is None else [uuid4() for _ in ids]
    handler = CreateInvitationHandler(
        unit_of_work_factory=lambda: uow,
        membership_query=memberships or _memberships(),
        email_lookup=email_lookup or FakeEmailLookup(),
        token_generator=_FakeTokenGen(tokens or ["raw-token-1"]),
        accept_url_builder=FakeAcceptUrlBuilder(),
        clock=FakeClock(_NOW),
        id_generator=FakeIdGenerator(id_values),
    )
    return handler, uow


class _FakeTokenGen:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = list(tokens)

    def new_raw_token(self) -> str:
        return self._tokens.pop(0)


def _create_command(actor: object, **kwargs: object) -> CreateInvitationCommand:
    return CreateInvitationCommand(
        tenant_id=TENANT,
        actor_user_id=actor,  # type: ignore[arg-type]
        invited_email=kwargs.get("email", "new.person@example.com"),  # type: ignore[arg-type]
        role=kwargs.get("role", "member"),  # type: ignore[arg-type]
        idempotency_key=kwargs.get("idempotency_key"),  # type: ignore[arg-type]
    )


# --- CreateInvitation --------------------------------------------------------


@pytest.mark.parametrize("actor", [OWNER, ADMIN])
def test_owner_and_admin_can_create(actor: object) -> None:
    handler, uow = _build_create(tokens=["raw-secret"])
    result = handler.handle(_create_command(actor))

    assert result.duplicate is False
    assert result.raw_token == "raw-secret"
    assert result.accept_url is not None and "raw-secret" in result.accept_url
    assert result.role == "member"
    assert result.status == "pending"
    assert uow.committed == 1
    assert len(uow.invitations.saved) == 1


def test_member_cannot_create() -> None:
    handler, uow = _build_create()
    with pytest.raises(PermissionDeniedError):
        handler.handle(_create_command(MEMBER))
    assert uow.committed == 0
    assert uow.invitations.saved == []


def test_non_member_cannot_create() -> None:
    handler, uow = _build_create()
    with pytest.raises(InvitationActorNotMemberError):
        handler.handle(_create_command(STRANGER))
    assert uow.committed == 0


def test_invalid_email_returns_domain_error() -> None:
    handler, _ = _build_create()
    with pytest.raises(InvalidInvitedEmailError):
        handler.handle(_create_command(OWNER, email="not-an-email"))


def test_owner_role_in_body_rejected() -> None:
    handler, _ = _build_create()
    with pytest.raises(InvitationRoleNotAllowedError):
        handler.handle(_create_command(OWNER, role="owner"))


def test_already_active_member_email_conflicts() -> None:
    existing_user = uuid4()
    memberships = FakeMembershipQuery({(TENANT, OWNER): "owner", (TENANT, existing_user): "member"})
    email_lookup = FakeEmailLookup({"taken@example.com": [existing_user]})
    handler, uow = _build_create(memberships=memberships, email_lookup=email_lookup)
    with pytest.raises(AlreadyActiveMemberError):
        handler.handle(_create_command(OWNER, email="taken@example.com"))
    assert uow.committed == 0


def test_duplicate_pending_invitation_conflicts() -> None:
    repo = FakeInvitationRepository(
        seed=[
            Invitation.create(
                id=InvitationId(uuid4()),
                tenant_id=TenantId(TENANT),
                invited_email="dup@example.com",
                role=MembershipRole.MEMBER,
                token_hash=hash_invitation_token("x"),
                invited_by_user_id=UserId(OWNER),
                created_at=_NOW,
            )
        ]
    )
    handler, uow = _build_create(repository=repo)
    with pytest.raises(DuplicatePendingInvitationError):
        handler.handle(_create_command(OWNER, email="dup@example.com"))
    assert uow.committed == 0


def _seed_expired_pending(email: str, *, created_at: datetime) -> Invitation:
    # created_at geçmişte → expires_at (created_at + 7g) da _NOW'a göre geçmişte olur.
    return Invitation.create(
        id=InvitationId(uuid4()),
        tenant_id=TenantId(TENANT),
        invited_email=email,
        role=MembershipRole.MEMBER,
        token_hash=hash_invitation_token("OLD-RAW"),
        invited_by_user_id=UserId(OWNER),
        created_at=created_at,
    )


def test_non_expired_pending_still_blocks_new_invite() -> None:
    repo = FakeInvitationRepository(
        seed=[_seed_expired_pending("keep@example.com", created_at=_NOW)]  # _NOW → expires future
    )
    handler, uow = _build_create(repository=repo)
    with pytest.raises(DuplicatePendingInvitationError):
        handler.handle(_create_command(OWNER, email="keep@example.com"))
    assert uow.committed == 0
    assert len(repo.saved) == 1  # eski davet dokunulmaz


def test_expired_pending_does_not_block_and_is_transitioned() -> None:
    old = _seed_expired_pending("again@example.com", created_at=_NOW - timedelta(days=8))
    repo = FakeInvitationRepository(seed=[old])
    audit = FakeAuditWriter()
    handler, uow = _build_create(repository=repo, audit=audit, tokens=["NEW-RAW"])

    result = handler.handle(_create_command(OWNER, email="again@example.com"))

    assert result.duplicate is False and result.raw_token == "NEW-RAW"
    assert uow.committed == 1
    # Eski davet expired oldu; yeni pending eklendi (farklı token hash).
    assert len(repo.saved) == 2
    old_row = next(i for i in repo.saved if i.id == old.id)
    new_row = next(i for i in repo.saved if i.id != old.id)
    assert old_row.status is InvitationStatus.EXPIRED
    assert old_row.version == old.version + 1
    assert new_row.status is InvitationStatus.PENDING
    assert new_row.token_hash == hash_invitation_token("NEW-RAW")
    assert new_row.token_hash != old.token_hash
    # Audit: önce expired, sonra created (ham token yok).
    events = [r.event_type.value for r in audit.records]
    assert events == ["organization.invitation.expired", "organization.invitation.created"]
    assert all("NEW-RAW" not in f"{r.metadata} {r.role_key}" for r in audit.records)
    assert all("OLD-RAW" not in f"{r.metadata} {r.role_key}" for r in audit.records)


def test_only_hash_persisted_never_raw_token() -> None:
    repo = FakeInvitationRepository()
    handler, _ = _build_create(repository=repo, tokens=["super-secret-raw"])
    result = handler.handle(_create_command(OWNER))
    saved = repo.saved[0]
    assert saved.token_hash == hash_invitation_token("super-secret-raw")
    assert saved.token_hash != "super-secret-raw"
    assert result.raw_token == "super-secret-raw"


def test_audit_written_without_token() -> None:
    audit = FakeAuditWriter()
    handler, _ = _build_create(audit=audit, tokens=["leak-me"])
    handler.handle(_create_command(OWNER, email="who@example.com"))
    assert len(audit.records) == 1
    record = audit.records[0]
    assert record.event_type.value == "organization.invitation.created"
    assert record.actor_user_id == OWNER
    assert record.metadata.get("invited_email") == "who@example.com"
    serialized = f"{record.metadata} {record.role_key}"
    assert "leak-me" not in serialized  # ham token audit'e girmez


def test_idempotency_replay_returns_duplicate_without_token() -> None:
    repo = FakeInvitationRepository()
    handler, _ = _build_create(repository=repo, tokens=["first-token", "second-token"])
    first = handler.handle(_create_command(OWNER, idempotency_key="key-1"))
    second = handler.handle(_create_command(OWNER, idempotency_key="key-1"))

    assert first.duplicate is False and first.raw_token == "first-token"
    assert second.duplicate is True
    assert second.raw_token is None and second.accept_url is None
    assert second.invitation_id == first.invitation_id
    assert len(repo.saved) == 1  # ikinci çağrı yeni kayıt oluşturmaz


def test_idempotency_key_reuse_with_different_payload_conflicts() -> None:
    repo = FakeInvitationRepository()
    handler, _ = _build_create(repository=repo, tokens=["t1", "t2"])
    handler.handle(_create_command(OWNER, email="a@example.com", idempotency_key="key-9"))
    with pytest.raises(IdempotencyKeyReuseError):
        handler.handle(_create_command(OWNER, email="b@example.com", idempotency_key="key-9"))


# --- ListPendingInvitations --------------------------------------------------


def _build_list(
    *,
    views: list[PendingInvitationView] | None = None,
    memberships: FakeMembershipQuery | None = None,
) -> tuple[ListPendingInvitationsHandler, FakeInvitationQuery]:
    query = FakeInvitationQuery(views)
    handler = ListPendingInvitationsHandler(
        invitation_query=query,
        membership_query=memberships or _memberships(),
        clock=FakeClock(_NOW),
    )
    return handler, query


def test_owner_lists_pending_with_clock_now() -> None:
    view = PendingInvitationView(
        invitation_id=uuid4(),
        invited_email="p@example.com",
        role="member",
        status="pending",
        expires_at=_NOW + timedelta(days=7),
        invited_by_user_id=OWNER,
        created_at=_NOW,
    )
    handler, query = _build_list(views=[view])
    items = handler.handle(tenant_id=TENANT, actor_user_id=OWNER, limit=50)
    assert items == [view]
    assert query.calls == [(TENANT, _NOW, 50)]


def test_member_cannot_list() -> None:
    handler, _ = _build_list()
    with pytest.raises(PermissionDeniedError):
        handler.handle(tenant_id=TENANT, actor_user_id=MEMBER, limit=50)


def test_non_member_cannot_list() -> None:
    handler, _ = _build_list()
    with pytest.raises(InvitationActorNotMemberError):
        handler.handle(tenant_id=TENANT, actor_user_id=STRANGER, limit=50)


# --- RevokeInvitation --------------------------------------------------------


def _seed_pending(tenant: object = TENANT, invitation_id: object = None) -> Invitation:
    return Invitation.create(
        id=InvitationId(invitation_id or uuid4()),  # type: ignore[arg-type]
        tenant_id=TenantId(tenant),  # type: ignore[arg-type]
        invited_email="revoke@example.com",
        role=MembershipRole.MEMBER,
        token_hash=hash_invitation_token("t"),
        invited_by_user_id=UserId(OWNER),
        created_at=_NOW,
    )


def _build_revoke(
    repo: FakeInvitationRepository, *, audit: FakeAuditWriter | None = None
) -> tuple[RevokeInvitationHandler, FakeInvitationUnitOfWork]:
    uow = FakeInvitationUnitOfWork(repo, audit or FakeAuditWriter())
    handler = RevokeInvitationHandler(
        unit_of_work_factory=lambda: uow,
        membership_query=_memberships(),
        clock=FakeClock(_NOW),
        id_generator=FakeIdGenerator([uuid4() for _ in range(5)]),
    )
    return handler, uow


def test_owner_revokes_pending() -> None:
    invitation = _seed_pending()
    repo = FakeInvitationRepository(seed=[invitation])
    audit = FakeAuditWriter()
    handler, uow = _build_revoke(repo, audit=audit)
    result = handler.handle(
        RevokeInvitationCommand(
            tenant_id=TENANT, actor_user_id=OWNER, invitation_id=invitation.id.value
        )
    )
    assert result.duplicate is False and result.status == "revoked"
    assert repo.saved[0].status is InvitationStatus.REVOKED
    assert repo.saved[0].version == 2  # optimistic CAS artırdı
    assert uow.committed == 1
    assert audit.records[0].event_type.value == "organization.invitation.revoked"


def test_revoke_replay_is_idempotent() -> None:
    invitation = replace(_seed_pending(), status=InvitationStatus.REVOKED)
    repo = FakeInvitationRepository(seed=[invitation])
    audit = FakeAuditWriter()
    handler, uow = _build_revoke(repo, audit=audit)
    result = handler.handle(
        RevokeInvitationCommand(
            tenant_id=TENANT, actor_user_id=OWNER, invitation_id=invitation.id.value
        )
    )
    assert result.duplicate is True and result.status == "revoked"
    assert uow.committed == 0  # yeni yazım yok
    assert audit.records == []  # idempotent replay audit üretmez


def test_revoke_unknown_invitation_not_found() -> None:
    repo = FakeInvitationRepository()
    handler, _ = _build_revoke(repo)
    with pytest.raises(InvitationNotFoundError):
        handler.handle(
            RevokeInvitationCommand(tenant_id=TENANT, actor_user_id=OWNER, invitation_id=uuid4())
        )


def test_cross_tenant_revoke_not_found() -> None:
    invitation = _seed_pending(tenant=OTHER_TENANT)
    repo = FakeInvitationRepository(seed=[invitation])
    # Actor TENANT owner'ı; davet OTHER_TENANT'ta → find_by_id(TENANT,...) None.
    handler, _ = _build_revoke(repo)
    with pytest.raises(InvitationNotFoundError):
        handler.handle(
            RevokeInvitationCommand(
                tenant_id=TENANT, actor_user_id=OWNER, invitation_id=invitation.id.value
            )
        )


def test_member_cannot_revoke() -> None:
    invitation = _seed_pending()
    repo = FakeInvitationRepository(seed=[invitation])
    handler, _ = _build_revoke(repo)
    with pytest.raises(PermissionDeniedError):
        handler.handle(
            RevokeInvitationCommand(
                tenant_id=TENANT, actor_user_id=MEMBER, invitation_id=invitation.id.value
            )
        )


def test_revoke_accepted_invitation_conflicts() -> None:
    invitation = replace(_seed_pending(), status=InvitationStatus.ACCEPTED)
    repo = FakeInvitationRepository(seed=[invitation])
    handler, _ = _build_revoke(repo)
    with pytest.raises(InvitationNotRevocableError):
        handler.handle(
            RevokeInvitationCommand(
                tenant_id=TENANT, actor_user_id=OWNER, invitation_id=invitation.id.value
            )
        )
