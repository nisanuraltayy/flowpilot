"""Davet kabul Idempotency-Key — GERÇEK PostgreSQL: concurrency, RLS, rollback.

flowpilot_app (NOBYPASSRLS): idempotency kaydı gerçek RLS + unique constraint'lerden geçer.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.organization.application.invitation_dto import (
    AcceptInvitationCommand,
    AcceptInvitationResult,
    CreateInvitationCommand,
)
from flowpilot.modules.organization.application.invitation_errors import (
    IdempotencyKeyReuseError,
    InvitationConcurrencyError,
    InvitationEmailMismatchError,
)
from tests.integration.invitation_support import (
    accept_idempotency_count,
    audit_event_count,
    build_accept_invitation_handler,
    build_create_invitation_handler,
    create_tenant_with_owner,
    membership_row,
    seed_identity,
)

pytestmark = pytest.mark.integration

INVITEE_EMAIL = "invitee@example.com"


def _create(app_sessionmaker: sessionmaker[Session], *, tenant_id: object, owner_id: object) -> str:
    created = build_create_invitation_handler(app_sessionmaker).handle(
        CreateInvitationCommand(
            tenant_id=tenant_id,  # type: ignore[arg-type]
            actor_user_id=owner_id,  # type: ignore[arg-type]
            invited_email=INVITEE_EMAIL,
            role="member",
        )
    )
    assert created.raw_token is not None
    return created.raw_token


def test_same_key_same_payload_replay(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="idem-1")
    token = _create(app_sessionmaker, tenant_id=tenant_id, owner_id=owner_id)
    invitee = seed_identity(app_sessionmaker, email=INVITEE_EMAIL)
    accept = build_accept_invitation_handler(app_sessionmaker)

    first = accept.handle(
        AcceptInvitationCommand(
            organization_id=tenant_id, actor_user_id=invitee, raw_token=token, idempotency_key="K1"
        )
    )
    second = accept.handle(
        AcceptInvitationCommand(
            organization_id=tenant_id, actor_user_id=invitee, raw_token=token, idempotency_key="K1"
        )
    )
    assert first.duplicate is False
    assert second.duplicate is True and second.membership_id == first.membership_id
    assert accept_idempotency_count(app_sessionmaker, tenant_id=tenant_id) == 1
    assert (
        audit_event_count(
            app_sessionmaker, tenant_id=tenant_id, event_type="organization.membership.joined"
        )
        == 1
    )


def test_same_key_different_token_conflicts(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="idem-2")
    token = _create(app_sessionmaker, tenant_id=tenant_id, owner_id=owner_id)
    invitee = seed_identity(app_sessionmaker, email=INVITEE_EMAIL)
    accept = build_accept_invitation_handler(app_sessionmaker)
    accept.handle(
        AcceptInvitationCommand(
            organization_id=tenant_id, actor_user_id=invitee, raw_token=token, idempotency_key="K2"
        )
    )
    # Aynı key, farklı token → 409 (fingerprint mismatch, state değişmez).
    with pytest.raises(IdempotencyKeyReuseError):
        accept.handle(
            AcceptInvitationCommand(
                organization_id=tenant_id,
                actor_user_id=invitee,
                raw_token="a-totally-different-token",
                idempotency_key="K2",
            )
        )
    assert accept_idempotency_count(app_sessionmaker, tenant_id=tenant_id) == 1


def test_same_key_different_org_conflicts(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_a, owner_a = create_tenant_with_owner(app_sessionmaker, owner_subject="idem-a")
    tenant_b, owner_b = create_tenant_with_owner(app_sessionmaker, owner_subject="idem-b")
    token_a = _create(app_sessionmaker, tenant_id=tenant_a, owner_id=owner_a)
    # B'de aynı invitee için bir davet (invitee her iki org'a da davet edilebilir).
    token_b = _create(app_sessionmaker, tenant_id=tenant_b, owner_id=owner_b)
    invitee = seed_identity(app_sessionmaker, email=INVITEE_EMAIL)
    accept = build_accept_invitation_handler(app_sessionmaker)

    accept.handle(
        AcceptInvitationCommand(
            organization_id=tenant_a,
            actor_user_id=invitee,
            raw_token=token_a,
            idempotency_key="SHARED",
        )
    )
    # Aynı key farklı org → 409 (actor-scoped cross-tenant tespit).
    with pytest.raises(IdempotencyKeyReuseError):
        accept.handle(
            AcceptInvitationCommand(
                organization_id=tenant_b,
                actor_user_id=invitee,
                raw_token=token_b,
                idempotency_key="SHARED",
            )
        )
    # B'de üyelik/idempotency kaydı OLUŞMADI.
    assert membership_row(app_sessionmaker, tenant_id=tenant_b, user_id=invitee) is None
    assert accept_idempotency_count(app_sessionmaker, tenant_id=tenant_b) == 0


def test_failed_accept_leaves_no_idempotency_record(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="idem-fail")
    token = _create(app_sessionmaker, tenant_id=tenant_id, owner_id=owner_id)
    wrong = seed_identity(app_sessionmaker, email="wrong@example.com")
    accept = build_accept_invitation_handler(app_sessionmaker)
    with pytest.raises(InvitationEmailMismatchError):
        accept.handle(
            AcceptInvitationCommand(
                organization_id=tenant_id,
                actor_user_id=wrong,
                raw_token=token,
                idempotency_key="KF",
            )
        )
    # Rollback: idempotency kaydı yok.
    assert accept_idempotency_count(app_sessionmaker, tenant_id=tenant_id) == 0


def test_cross_tenant_idempotency_record_not_readable(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_a, owner_a = create_tenant_with_owner(app_sessionmaker, owner_subject="idem-iso-a")
    tenant_b, owner_b = create_tenant_with_owner(app_sessionmaker, owner_subject="idem-iso-b")
    token = _create(app_sessionmaker, tenant_id=tenant_a, owner_id=owner_a)
    invitee = seed_identity(app_sessionmaker, email=INVITEE_EMAIL)
    build_accept_invitation_handler(app_sessionmaker).handle(
        AcceptInvitationCommand(
            organization_id=tenant_a, actor_user_id=invitee, raw_token=token, idempotency_key="ISO"
        )
    )
    # Tenant B context + owner_b actor: A'nın idempotency kaydını GÖREMEZ.
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_b)}
        )
        s.execute(text("SELECT set_config('app.current_actor_id', :a, true)"), {"a": str(owner_b)})
        count = s.execute(
            text("SELECT count(*) FROM organization_invitation_accept_idempotency")
        ).scalar_one()
    assert count == 0
    # Context YOKKEN default deny.
    with app_sessionmaker() as s, s.begin():
        deny = s.execute(
            text("SELECT count(*) FROM organization_invitation_accept_idempotency")
        ).scalar_one()
    assert deny == 0


def test_concurrent_same_key_single_record_and_membership(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="idem-race")
    token = _create(app_sessionmaker, tenant_id=tenant_id, owner_id=owner_id)
    invitee = seed_identity(app_sessionmaker, email=INVITEE_EMAIL)
    accept = build_accept_invitation_handler(app_sessionmaker)

    def attempt(_: int) -> object:
        try:
            return accept.handle(
                AcceptInvitationCommand(
                    organization_id=tenant_id,
                    actor_user_id=invitee,
                    raw_token=token,
                    idempotency_key="RACE",
                )
            )
        except (InvitationConcurrencyError, IdempotencyKeyReuseError) as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))

    winners = [o for o in outcomes if isinstance(o, AcceptInvitationResult) and not o.duplicate]
    assert len(winners) == 1, f"tek kazanan bekleniyordu: {outcomes}"
    # Tek üyelik, tek idempotency kaydı, tek accepted + tek joined audit.
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        m = s.execute(
            text(
                "SELECT count(*) FROM organization_memberships "
                "WHERE tenant_id = :t AND user_id = :u"
            ),
            {"t": str(tenant_id), "u": str(invitee)},
        ).scalar_one()
    assert m == 1
    assert accept_idempotency_count(app_sessionmaker, tenant_id=tenant_id) == 1
    assert (
        audit_event_count(
            app_sessionmaker, tenant_id=tenant_id, event_type="organization.invitation.accepted"
        )
        == 1
    )
    assert (
        audit_event_count(
            app_sessionmaker, tenant_id=tenant_id, event_type="organization.membership.joined"
        )
        == 1
    )
