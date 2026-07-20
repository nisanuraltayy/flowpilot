"""Davet kabulü — GERÇEK PostgreSQL: atomiklik, tenant izolasyonu, concurrency, pin.

flowpilot_app (NOBYPASSRLS): kabul + üyelik + audit gerçek RLS + unique constraint'lerden
geçer. Ham token DB'de bulunmaz.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.organization.application.invitation_dto import (
    AcceptInvitationCommand,
    AcceptInvitationResult,
    CreateInvitationCommand,
)
from flowpilot.modules.organization.application.invitation_errors import (
    InvitationAcceptedByOtherError,
    InvitationConcurrencyError,
    InvitationEmailMismatchError,
    InvitationNotFoundError,
)
from tests.integration.invitation_support import (
    audit_event_count,
    build_accept_invitation_handler,
    build_create_invitation_handler,
    create_tenant_with_owner,
    membership_row,
    seed_identity,
)

pytestmark = pytest.mark.integration

INVITEE_EMAIL = "invitee@example.com"


def _create_invitation(
    app_sessionmaker: sessionmaker[Session],
    *,
    tenant_id: object,
    owner_id: object,
    email: str = INVITEE_EMAIL,
    role: str = "member",
) -> str:
    created = build_create_invitation_handler(app_sessionmaker).handle(
        CreateInvitationCommand(
            tenant_id=tenant_id,  # type: ignore[arg-type]
            actor_user_id=owner_id,  # type: ignore[arg-type]
            invited_email=email,
            role=role,
        )
    )
    assert created.raw_token is not None
    return created.raw_token


def test_accept_creates_active_membership_and_audit_atomic(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="acc-owner")
    token = _create_invitation(app_sessionmaker, tenant_id=tenant_id, owner_id=owner_id)
    invitee = seed_identity(app_sessionmaker, email=INVITEE_EMAIL)

    result = build_accept_invitation_handler(app_sessionmaker).handle(
        AcceptInvitationCommand(organization_id=tenant_id, actor_user_id=invitee, raw_token=token)
    )
    assert result.duplicate is False and result.role == "member" and result.status == "active"

    membership = membership_row(app_sessionmaker, tenant_id=tenant_id, user_id=invitee)
    assert (
        membership is not None
        and membership["role"] == "member"
        and membership["status"] == "active"
    )
    # Davet accepted + accepted_by pinlendi; ham token DB'de yok.
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        row = s.execute(
            text(
                "SELECT status, accepted_by_user_id, id::text||token_hash AS blob "
                "FROM organization_invitations WHERE tenant_id = :t"
            ),
            {"t": str(tenant_id)},
        ).one()
    assert row.status == "accepted"
    assert str(row.accepted_by_user_id) == str(invitee)
    assert token not in row.blob
    # Audit: accepted + membership.joined AYNI transaction.
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


def test_failed_email_match_leaves_no_partial_state(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="acc-fail")
    token = _create_invitation(app_sessionmaker, tenant_id=tenant_id, owner_id=owner_id)
    wrong = seed_identity(app_sessionmaker, email="not-the-invitee@example.com")

    with pytest.raises(InvitationEmailMismatchError):
        build_accept_invitation_handler(app_sessionmaker).handle(
            AcceptInvitationCommand(organization_id=tenant_id, actor_user_id=wrong, raw_token=token)
        )
    # Yarım state yok: davet hâlâ pending, üyelik yok, audit yok.
    assert membership_row(app_sessionmaker, tenant_id=tenant_id, user_id=wrong) is None
    assert (
        audit_event_count(
            app_sessionmaker, tenant_id=tenant_id, event_type="organization.invitation.accepted"
        )
        == 0
    )
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        status = s.execute(
            text("SELECT status FROM organization_invitations WHERE tenant_id = :t"),
            {"t": str(tenant_id)},
        ).scalar_one()
    assert status == "pending"


def test_cross_tenant_token_rejected(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_a, owner_a = create_tenant_with_owner(app_sessionmaker, owner_subject="acc-a")
    tenant_b, _ = create_tenant_with_owner(app_sessionmaker, owner_subject="acc-b")
    token = _create_invitation(app_sessionmaker, tenant_id=tenant_a, owner_id=owner_a)
    invitee = seed_identity(app_sessionmaker, email=INVITEE_EMAIL)
    # A'nın token'ı B context'inde → RLS scope → bulunamaz → 404.
    with pytest.raises(InvitationNotFoundError):
        build_accept_invitation_handler(app_sessionmaker).handle(
            AcceptInvitationCommand(
                organization_id=tenant_b, actor_user_id=invitee, raw_token=token
            )
        )


def test_accepted_invitation_pinned_to_single_actor(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="acc-pin")
    token = _create_invitation(app_sessionmaker, tenant_id=tenant_id, owner_id=owner_id)
    invitee = seed_identity(app_sessionmaker, email=INVITEE_EMAIL)
    accept = build_accept_invitation_handler(app_sessionmaker)
    accept.handle(
        AcceptInvitationCommand(organization_id=tenant_id, actor_user_id=invitee, raw_token=token)
    )

    # Aynı actor replay → duplicate (yeni üyelik yok).
    replay = accept.handle(
        AcceptInvitationCommand(organization_id=tenant_id, actor_user_id=invitee, raw_token=token)
    )
    assert replay.duplicate is True

    # Farklı actor (e-postası da eşleşse bile) accepted daveti kullanamaz → 404.
    other = seed_identity(app_sessionmaker, email=INVITEE_EMAIL)
    with pytest.raises(InvitationAcceptedByOtherError):
        accept.handle(
            AcceptInvitationCommand(organization_id=tenant_id, actor_user_id=other, raw_token=token)
        )


def test_concurrent_accepts_single_membership(app_sessionmaker: sessionmaker[Session]) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="acc-race")
    token = _create_invitation(app_sessionmaker, tenant_id=tenant_id, owner_id=owner_id)
    invitee = seed_identity(app_sessionmaker, email=INVITEE_EMAIL)
    accept = build_accept_invitation_handler(app_sessionmaker)

    def attempt(_: int) -> object:
        try:
            return accept.handle(
                AcceptInvitationCommand(
                    organization_id=tenant_id, actor_user_id=invitee, raw_token=token
                )
            )
        except (InvitationConcurrencyError, InvitationAcceptedByOtherError) as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))

    winners = [o for o in outcomes if isinstance(o, AcceptInvitationResult) and not o.duplicate]
    assert len(winners) == 1, f"tam olarak bir kazanan bekleniyordu: {outcomes}"
    # Tam olarak BİR üyelik (unique(tenant_id,user_id) + CAS).
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        count = s.execute(
            text(
                "SELECT count(*) FROM organization_memberships "
                "WHERE tenant_id = :t AND user_id = :u"
            ),
            {"t": str(tenant_id), "u": str(invitee)},
        ).scalar_one()
    assert count == 1


def test_existing_active_member_accept_keeps_role_no_new_membership(
    app_sessionmaker: sessionmaker[Session],
) -> None:
    tenant_id, owner_id = create_tenant_with_owner(app_sessionmaker, owner_subject="acc-exist")
    # Davet ADMIN rolü ile oluşturulur ama davetli zaten member; rol YÜKSELTİLMEZ.
    token = _create_invitation(
        app_sessionmaker, tenant_id=tenant_id, owner_id=owner_id, email=INVITEE_EMAIL, role="admin"
    )
    # Davetliyi önce member olarak ekle (identity + membership) — aynı e-posta.
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
    invitee = seed_identity(app_sessionmaker, email=INVITEE_EMAIL)
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        s.execute(
            text(
                "INSERT INTO organization_memberships (id, tenant_id, user_id, role, status, "
                "created_at, updated_at, version) "
                "VALUES (:id, :t, :u, 'member', 'active', now(), now(), 1)"
            ),
            {"id": str(uuid4()), "t": str(tenant_id), "u": str(invitee)},
        )

    result = build_accept_invitation_handler(app_sessionmaker).handle(
        AcceptInvitationCommand(organization_id=tenant_id, actor_user_id=invitee, raw_token=token)
    )
    assert result.duplicate is True
    assert result.role == "member"  # admin'e YÜKSELTİLMEDİ
    # Tek üyelik, hâlâ member; davet accepted; membership.joined audit YOK.
    membership = membership_row(app_sessionmaker, tenant_id=tenant_id, user_id=invitee)
    assert membership is not None and membership["role"] == "member"
    assert (
        audit_event_count(
            app_sessionmaker, tenant_id=tenant_id, event_type="organization.membership.joined"
        )
        == 0
    )
    assert (
        audit_event_count(
            app_sessionmaker, tenant_id=tenant_id, event_type="organization.invitation.accepted"
        )
        == 1
    )
