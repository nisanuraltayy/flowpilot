"""Invitation repository + RLS — GERÇEK PostgreSQL. Tenant izolasyonu, token-at-rest.

flowpilot_app (NOBYPASSRLS) rolüyle: davet yazımı/okuması gerçek RLS policy'lerinden geçer.
"""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.api.wiring import SqlAlchemyInvitationUnitOfWork
from flowpilot.modules.organization.application.invitation_dto import (
    CreateInvitationCommand,
    CreateInvitationResult,
)
from flowpilot.modules.organization.application.invitation_errors import (
    DuplicatePendingInvitationError,
    InvitationConcurrencyError,
)
from flowpilot.modules.organization.domain.invitation import Invitation, InvitationStatus
from flowpilot.modules.organization.domain.invitation_token import hash_invitation_token
from flowpilot.modules.organization.domain.membership import MembershipRole
from flowpilot.modules.organization.infrastructure.persistence.invitation_query import (
    SqlAlchemyInvitationQuery,
)
from flowpilot.modules.organization.infrastructure.persistence.invitation_repository import (
    SqlAlchemyInvitationRepository,
)
from flowpilot.shared.clock import SystemClock
from flowpilot.shared.identifiers import InvitationId, TenantId, UserId
from tests.integration.invitation_support import (
    build_create_invitation_handler,
    create_tenant_with_owner,
    force_past_expiry,
)

pytestmark = pytest.mark.integration

RAW_TOKEN = "raw-token-do-not-store"


def _new_invitation(
    tenant_id: UUID, owner_id: UUID, *, email: str = "invitee@example.com"
) -> Invitation:
    return Invitation.create(
        id=InvitationId(uuid4()),
        tenant_id=TenantId(tenant_id),
        invited_email=email,
        role=MembershipRole.MEMBER,
        token_hash=hash_invitation_token(RAW_TOKEN),
        invited_by_user_id=UserId(owner_id),
        created_at=SystemClock().now(),
    )


def _insert(
    app_sessionmaker: sessionmaker[Session], tenant_id: UUID, invitation: Invitation
) -> None:
    with SqlAlchemyInvitationUnitOfWork(app_sessionmaker) as uow:
        uow.set_actor_context(invitation.invited_by_user_id.value)
        uow.set_tenant_context(tenant_id)
        uow.invitations.add(invitation, idempotency_key=None, request_fingerprint=None)
        uow.commit()


def test_only_hash_persisted_never_raw_token(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="s-owner")
    invitation = _new_invitation(tenant_id, owner_id)
    _insert(app_sessionmaker, tenant_id, invitation)

    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        row = s.execute(
            text("SELECT token_hash FROM organization_invitations WHERE tenant_id = :t"),
            {"t": str(tenant_id)},
        ).one()
        # Ham token HİÇBİR kolonda görünmez (metin taraması).
        full = s.execute(
            text(
                "SELECT id::text || invited_email || role || token_hash || status "
                "FROM organization_invitations WHERE tenant_id = :t"
            ),
            {"t": str(tenant_id)},
        ).scalar_one()
    assert row[0] == hashlib.sha256(RAW_TOKEN.encode()).hexdigest()
    assert RAW_TOKEN not in str(full)


def test_tenant_cannot_see_other_tenant_invitations(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_a, owner_a = create_tenant_with_owner(app_sessionmaker, owner_subject="s-a")
    tenant_b, _ = create_tenant_with_owner(app_sessionmaker, owner_subject="s-b")
    _insert(app_sessionmaker, tenant_a, _new_invitation(tenant_a, owner_a))

    query = SqlAlchemyInvitationQuery(app_sessionmaker)
    now = SystemClock().now()
    assert len(query.list_pending(tenant_id=tenant_a, now=now, limit=50)) == 1
    assert query.list_pending(tenant_id=tenant_b, now=now, limit=50) == []


def test_cross_tenant_find_by_id_denied_by_rls(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_a, owner_a = create_tenant_with_owner(app_sessionmaker, owner_subject="s-a2")
    tenant_b, _ = create_tenant_with_owner(app_sessionmaker, owner_subject="s-b2")
    invitation = _new_invitation(tenant_a, owner_a)
    _insert(app_sessionmaker, tenant_a, invitation)

    # Tenant B context'inde A'nın davetini id ile aramak → RLS boş döndürür (None).
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_b)}
        )
        repo = SqlAlchemyInvitationRepository(s)
        assert repo.find_by_id(tenant_id=tenant_a, invitation_id=invitation.id.value) is None


def test_rls_default_deny_without_context(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_a, owner_a = create_tenant_with_owner(app_sessionmaker, owner_subject="s-a3")
    _insert(app_sessionmaker, tenant_a, _new_invitation(tenant_a, owner_a))
    # Context YOKKEN hiçbir satır görünmez.
    with app_sessionmaker() as s, s.begin():
        count = s.execute(text("SELECT count(*) FROM organization_invitations")).scalar_one()
    assert count == 0


def test_update_policy_allows_revoke_and_bumps_version(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_a, owner_a = create_tenant_with_owner(app_sessionmaker, owner_subject="s-a4")
    invitation = _new_invitation(tenant_a, owner_a)
    _insert(app_sessionmaker, tenant_a, invitation)

    revoked = invitation.revoke(now=SystemClock().now())
    with SqlAlchemyInvitationUnitOfWork(app_sessionmaker) as uow:
        uow.set_actor_context(owner_a)
        uow.set_tenant_context(tenant_a)
        uow.invitations.update_checked(revoked, expected_version=invitation.version)
        uow.commit()

    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_a)}
        )
        row = s.execute(
            text("SELECT status, version FROM organization_invitations WHERE id = :i"),
            {"i": str(invitation.id.value)},
        ).one()
    assert row[0] == InvitationStatus.REVOKED.value
    assert row[1] == invitation.version + 1


def test_stale_version_update_conflicts(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_a, owner_a = create_tenant_with_owner(app_sessionmaker, owner_subject="s-a5")
    invitation = _new_invitation(tenant_a, owner_a)
    _insert(app_sessionmaker, tenant_a, invitation)
    revoked = invitation.revoke(now=SystemClock().now())
    with SqlAlchemyInvitationUnitOfWork(app_sessionmaker) as uow:
        uow.set_actor_context(owner_a)
        uow.set_tenant_context(tenant_a)
        with pytest.raises(InvitationConcurrencyError):
            uow.invitations.update_checked(revoked, expected_version=invitation.version + 5)


def test_concurrent_reinvite_single_winner(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="s-race")
    handler = build_create_invitation_handler(app_sessionmaker)
    email = "race@example.com"

    first = handler.handle(
        CreateInvitationCommand(
            tenant_id=tenant_id, actor_user_id=owner_id, invited_email=email, role="member"
        )
    )
    force_past_expiry(app_sessionmaker, tenant_id=tenant_id, invitation_id=first.invitation_id)

    def attempt(_: int) -> object:
        try:
            return handler.handle(
                CreateInvitationCommand(
                    tenant_id=tenant_id, actor_user_id=owner_id, invited_email=email, role="member"
                )
            )
        except (InvitationConcurrencyError, DuplicatePendingInvitationError) as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))

    winners = [o for o in outcomes if isinstance(o, CreateInvitationResult) and not o.duplicate]
    assert len(winners) == 1, f"tam olarak bir kazanan bekleniyordu: {outcomes}"
    # Sonuçta AYNI e-posta için tam olarak BİR bekleyen davet kalır (partial unique + CAS).
    pending = SqlAlchemyInvitationQuery(app_sessionmaker).list_pending(
        tenant_id=tenant_id, now=SystemClock().now(), limit=50
    )
    assert len([p for p in pending if p.invited_email == email]) == 1
