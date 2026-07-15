"""EnsureAuthenticatedUser use-case testleri (deterministik fake'lerle)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from flowpilot.modules.identity.application.auth import AuthenticatedIdentity
from flowpilot.modules.identity.application.ensure_user import EnsureAuthenticatedUserHandler
from flowpilot.modules.identity.domain.auth_provider import AuthProvider
from flowpilot.modules.identity.domain.user import User
from flowpilot.shared.identifiers import UserId
from tests.unit.fakes import FakeClock, FakeIdentityUnitOfWork, FakeIdGenerator, FakeUserRepository

FIXED_NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)
NEW_USER_UUID = UUID("33333333-3333-3333-3333-333333333333")
EXISTING_USER_UUID = UUID("44444444-4444-4444-4444-444444444444")
RACE_WINNER_UUID = UUID("55555555-5555-5555-5555-555555555555")


def _identity(subject: str = "sub-1", email: str | None = "a@example.com") -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider=AuthProvider.SUPABASE,
        provider_subject=subject,
        email=email,
        token_expires_at=FIXED_NOW + timedelta(minutes=10),
    )


def _handler(repo: FakeUserRepository) -> EnsureAuthenticatedUserHandler:
    return EnsureAuthenticatedUserHandler(
        unit_of_work_factory=lambda: FakeIdentityUnitOfWork(repo),
        clock=FakeClock(FIXED_NOW),
        id_generator=FakeIdGenerator([NEW_USER_UUID]),
    )


def _existing_user(subject: str = "sub-1") -> User:
    return User(
        id=UserId(EXISTING_USER_UUID),
        auth_provider=AuthProvider.SUPABASE,
        provider_subject=subject,
        email_snapshot="old@example.com",
        created_at=FIXED_NOW,
    )


def test_first_authentication_creates_internal_user() -> None:
    repo = FakeUserRepository()

    user_id = _handler(repo).handle(_identity())

    assert user_id == NEW_USER_UUID
    assert len(repo.users) == 1
    created = repo.users[0]
    assert created.auth_provider is AuthProvider.SUPABASE
    assert created.provider_subject == "sub-1"
    assert created.email_snapshot == "a@example.com"
    assert created.created_at == FIXED_NOW


def test_same_subject_returns_same_internal_user() -> None:
    repo = FakeUserRepository()
    repo.users.append(_existing_user())

    user_id = _handler(repo).handle(_identity())

    assert user_id == EXISTING_USER_UUID
    assert len(repo.users) == 1  # yeni kayit OLUSMADI
    assert repo.add_attempts == 0


def test_changed_email_does_not_create_new_user() -> None:
    repo = FakeUserRepository()
    repo.users.append(_existing_user())

    user_id = _handler(repo).handle(_identity(email="brand-new@example.com"))

    assert user_id == EXISTING_USER_UUID
    assert len(repo.users) == 1  # e-posta identity DEGILDIR


def test_concurrent_duplicate_resolves_to_winner() -> None:
    # add() aninda baska bir istek ayni subject'i insert etmis gibi davranir:
    # unique constraint ihlali -> handler kazananin kaydini okur.
    winner = User(
        id=UserId(RACE_WINNER_UUID),
        auth_provider=AuthProvider.SUPABASE,
        provider_subject="sub-1",
        email_snapshot="winner@example.com",
        created_at=FIXED_NOW,
    )
    repo = FakeUserRepository(race_inserts=[winner])

    user_id = _handler(repo).handle(_identity())

    assert user_id == RACE_WINNER_UUID
    assert repo.add_attempts == 1
    assert len(repo.users) == 1  # kaybedenin kaydi YOK
