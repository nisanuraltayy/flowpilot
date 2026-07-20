"""Invitation domain birim testleri — token, normalize, rol, expiry, revoke."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from flowpilot.modules.organization.domain.invitation import (
    INVITATION_TTL,
    InvalidInvitedEmailError,
    Invitation,
    InvitationNotAcceptableError,
    InvitationNotRevocableError,
    InvitationRoleNotAllowedError,
    InvitationStatus,
    invitation_role_from,
    normalize_invited_email,
)
from flowpilot.modules.organization.domain.invitation_token import (
    hash_invitation_token,
    invitation_request_fingerprint,
)
from flowpilot.modules.organization.domain.membership import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from flowpilot.modules.organization.infrastructure.token_generator import (
    SecretsInvitationTokenGenerator,
)
from flowpilot.shared.identifiers import InvitationId, MembershipId, TenantId, UserId

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _pending(role: MembershipRole = MembershipRole.MEMBER) -> Invitation:
    return Invitation.create(
        id=InvitationId(uuid4()),
        tenant_id=TenantId(uuid4()),
        invited_email="user@example.com",
        role=role,
        token_hash=hash_invitation_token("raw-token"),
        invited_by_user_id=UserId(uuid4()),
        created_at=_NOW,
    )


# --- token güvenliği ---------------------------------------------------------


def test_hash_is_deterministic() -> None:
    assert hash_invitation_token("abc") == hash_invitation_token("abc")


def test_hash_differs_from_raw_and_is_sha256_hex() -> None:
    raw = "some-raw-token"
    hashed = hash_invitation_token(raw)
    assert hashed != raw
    assert len(hashed) == 64
    assert all(c in "0123456789abcdef" for c in hashed)


def test_secure_token_generator_produces_unique_nonempty_tokens() -> None:
    generator = SecretsInvitationTokenGenerator()
    tokens = {generator.new_raw_token() for _ in range(50)}
    assert len(tokens) == 50  # çakışma yok
    assert all(t for t in tokens)  # boş değil


def test_request_fingerprint_is_deterministic_and_hashes_pii() -> None:
    fp1 = invitation_request_fingerprint(invited_email="a@b.com", role="member")
    fp2 = invitation_request_fingerprint(invited_email="a@b.com", role="member")
    assert fp1 == fp2 and len(fp1) == 64
    assert "a@b.com" not in fp1  # ham e-posta fingerprint'te yok
    assert fp1 != invitation_request_fingerprint(invited_email="a@b.com", role="admin")


# --- e-posta normalizasyonu --------------------------------------------------


def test_email_is_trimmed_and_lowercased() -> None:
    assert normalize_invited_email("  Foo.Bar@Example.COM  ") == "foo.bar@example.com"


@pytest.mark.parametrize("bad", ["", "   ", "nope", "a@b", "@example.com", "user@", "user@x."])
def test_invalid_email_raises(bad: str) -> None:
    with pytest.raises(InvalidInvitedEmailError):
        normalize_invited_email(bad)


# --- rol kuralları -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("admin", MembershipRole.ADMIN),
        ("member", MembershipRole.MEMBER),
        ("  Admin ", MembershipRole.ADMIN),
    ],
)
def test_admin_member_roles_accepted(raw: str, expected: MembershipRole) -> None:
    assert invitation_role_from(raw) is expected


@pytest.mark.parametrize("raw", ["owner", "OWNER", "boss", ""])
def test_owner_and_unknown_roles_rejected(raw: str) -> None:
    with pytest.raises(InvitationRoleNotAllowedError):
        invitation_role_from(raw)


def test_create_rejects_owner_role_defense_in_depth() -> None:
    with pytest.raises(InvitationRoleNotAllowedError):
        Invitation.create(
            id=InvitationId(uuid4()),
            tenant_id=TenantId(uuid4()),
            invited_email="user@example.com",
            role=MembershipRole.OWNER,
            token_hash=hash_invitation_token("raw"),
            invited_by_user_id=UserId(uuid4()),
            created_at=_NOW,
        )


# --- oluşturma + expiry ------------------------------------------------------


def test_create_sets_pending_status_and_seven_day_expiry() -> None:
    invitation = _pending()
    assert invitation.status is InvitationStatus.PENDING
    assert invitation.version == 1
    assert invitation.expires_at == _NOW + timedelta(days=7)
    assert INVITATION_TTL == timedelta(days=7)  # noqa: SIM300
    assert invitation.updated_at == _NOW


def test_is_expired_boundary() -> None:
    invitation = _pending()
    assert invitation.is_expired(_NOW + timedelta(days=6, hours=23)) is False
    assert invitation.is_expired(invitation.expires_at) is True
    assert invitation.is_expired(_NOW + timedelta(days=8)) is True


# --- revoke geçişi -----------------------------------------------------------


def test_revoke_pending_becomes_revoked() -> None:
    invitation = _pending()
    later = _NOW + timedelta(hours=1)
    revoked = invitation.revoke(now=later)
    assert revoked.status is InvitationStatus.REVOKED
    assert revoked.updated_at == later
    assert revoked.version == invitation.version  # CAS beklenen sürüm; repo artırır


def test_revoke_accepted_raises() -> None:
    from dataclasses import replace

    accepted = replace(_pending(), status=InvitationStatus.ACCEPTED)
    with pytest.raises(InvitationNotRevocableError):
        accepted.revoke(now=_NOW)


def test_revoke_expired_raises_terminal() -> None:
    from dataclasses import replace

    expired = replace(_pending(), status=InvitationStatus.EXPIRED)
    with pytest.raises(InvitationNotRevocableError):
        expired.revoke(now=_NOW)


def test_expire_pending_becomes_expired() -> None:
    invitation = _pending()
    later = invitation.expires_at + timedelta(hours=1)
    expired = invitation.expire(now=later)
    assert expired.status is InvitationStatus.EXPIRED
    assert expired.updated_at == later
    assert expired.version == invitation.version  # CAS beklenen sürüm; repo artırır


def test_expire_non_pending_raises() -> None:
    from dataclasses import replace

    revoked = replace(_pending(), status=InvitationStatus.REVOKED)
    with pytest.raises(InvitationNotRevocableError):
        revoked.expire(now=_NOW)


# --- accept geçişi -----------------------------------------------------------


def test_accept_pending_sets_accepted_fields() -> None:
    invitation = _pending()
    actor = UserId(uuid4())
    later = _NOW + timedelta(hours=2)
    accepted = invitation.accept(accepted_by=actor, now=later)
    assert accepted.status is InvitationStatus.ACCEPTED
    assert accepted.accepted_by_user_id == actor
    assert accepted.accepted_at == later
    assert accepted.updated_at == later
    assert accepted.version == invitation.version  # CAS beklenen sürüm; repo artırır


@pytest.mark.parametrize(
    "status",
    [InvitationStatus.ACCEPTED, InvitationStatus.REVOKED, InvitationStatus.EXPIRED],
)
def test_accept_non_pending_raises(status: InvitationStatus) -> None:
    from dataclasses import replace

    terminal = replace(_pending(), status=status)
    with pytest.raises(InvitationNotAcceptableError):
        terminal.accept(accepted_by=UserId(uuid4()), now=_NOW)


# --- active membership factory ----------------------------------------------


@pytest.mark.parametrize("role", [MembershipRole.ADMIN, MembershipRole.MEMBER])
def test_create_active_membership_admin_member(role: MembershipRole) -> None:
    membership = Membership.create_active(
        id=MembershipId(uuid4()),
        tenant_id=TenantId(uuid4()),
        user_id=UserId(uuid4()),
        role=role,
        created_at=_NOW,
    )
    assert membership.role is role
    assert membership.status is MembershipStatus.ACTIVE


def test_create_active_membership_rejects_owner() -> None:
    with pytest.raises(ValueError, match="owner"):
        Membership.create_active(
            id=MembershipId(uuid4()),
            tenant_id=TenantId(uuid4()),
            user_id=UserId(uuid4()),
            role=MembershipRole.OWNER,
            created_at=_NOW,
        )
