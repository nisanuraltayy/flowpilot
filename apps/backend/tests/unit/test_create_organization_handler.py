"""CreateOrganizationHandler unit testleri (deterministik fake'lerle).

Gerçek DB yok — atomiklik burada handler'ın commit/rollback ÇAĞRI davranışıyla
doğrulanır; gerçek transaction rollback'i integration testlerde kanıtlanır.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from flowpilot.modules.organization.application.commands import CreateOrganizationCommand
from flowpilot.modules.organization.application.errors import ActorNotFoundError
from flowpilot.modules.organization.application.handler import CreateOrganizationHandler
from flowpilot.modules.organization.domain.errors import (
    EmptyOrganizationNameError,
    OrganizationNameTooLongError,
)
from flowpilot.modules.organization.domain.membership import (
    MembershipRole,
    MembershipStatus,
)
from tests.unit.fakes import (
    FakeClock,
    FakeIdGenerator,
    FakeOrganizationRepository,
    FakeUnitOfWork,
    FakeUserDirectory,
)

FIXED_NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)
TENANT_UUID = UUID("11111111-1111-1111-1111-111111111111")
MEMBERSHIP_UUID = UUID("22222222-2222-2222-2222-222222222222")


def _handler(
    *,
    repository: FakeOrganizationRepository,
    uow: FakeUnitOfWork,
    actor: UUID,
    actor_exists: bool = True,
) -> CreateOrganizationHandler:
    existing = [actor] if actor_exists else []
    return CreateOrganizationHandler(
        unit_of_work=uow,
        user_directory=FakeUserDirectory(existing),
        clock=FakeClock(FIXED_NOW),
        id_generator=FakeIdGenerator([TENANT_UUID, MEMBERSHIP_UUID]),
    )


def test_creates_tenant_and_owner_membership() -> None:
    actor = uuid4()
    repo = FakeOrganizationRepository()
    uow = FakeUnitOfWork(repo)
    handler = _handler(repository=repo, uow=uow, actor=actor)

    result = handler.handle(CreateOrganizationCommand(actor, "Acme"))

    assert result.tenant_id == TENANT_UUID
    assert result.owner_membership_id == MEMBERSHIP_UUID
    assert uow.committed is True
    assert uow.rolled_back is False

    assert len(repo.tenants) == 1
    assert len(repo.memberships) == 1
    membership = repo.memberships[0]
    assert membership.role is MembershipRole.OWNER
    assert membership.status is MembershipStatus.ACTIVE
    assert membership.tenant_id.value == TENANT_UUID
    assert membership.user_id.value == actor


def test_deterministic_clock_and_ids_are_used() -> None:
    actor = uuid4()
    repo = FakeOrganizationRepository()
    uow = FakeUnitOfWork(repo)
    handler = _handler(repository=repo, uow=uow, actor=actor)

    handler.handle(CreateOrganizationCommand(actor, "Acme"))

    assert repo.tenants[0].id.value == TENANT_UUID
    assert repo.tenants[0].created_at == FIXED_NOW
    assert repo.memberships[0].created_at == FIXED_NOW


def test_rls_contexts_are_set_for_actor_then_tenant() -> None:
    actor = uuid4()
    repo = FakeOrganizationRepository()
    uow = FakeUnitOfWork(repo)
    handler = _handler(repository=repo, uow=uow, actor=actor)

    handler.handle(CreateOrganizationCommand(actor, "Acme"))

    assert uow.actor_context == actor
    assert uow.tenant_context == TENANT_UUID


def test_empty_name_is_rejected_before_transaction() -> None:
    actor = uuid4()
    repo = FakeOrganizationRepository()
    uow = FakeUnitOfWork(repo)
    handler = _handler(repository=repo, uow=uow, actor=actor)

    with pytest.raises(EmptyOrganizationNameError):
        handler.handle(CreateOrganizationCommand(actor, ""))

    assert uow.entered is False
    assert uow.committed is False


def test_whitespace_only_name_is_rejected() -> None:
    actor = uuid4()
    repo = FakeOrganizationRepository()
    uow = FakeUnitOfWork(repo)
    handler = _handler(repository=repo, uow=uow, actor=actor)

    with pytest.raises(EmptyOrganizationNameError):
        handler.handle(CreateOrganizationCommand(actor, "   "))
    assert uow.committed is False


def test_too_long_name_is_rejected() -> None:
    actor = uuid4()
    repo = FakeOrganizationRepository()
    uow = FakeUnitOfWork(repo)
    handler = _handler(repository=repo, uow=uow, actor=actor)

    with pytest.raises(OrganizationNameTooLongError):
        handler.handle(CreateOrganizationCommand(actor, "a" * 201))
    assert uow.committed is False


def test_missing_actor_is_rejected_and_rolls_back() -> None:
    actor = uuid4()
    repo = FakeOrganizationRepository()
    uow = FakeUnitOfWork(repo)
    handler = _handler(repository=repo, uow=uow, actor=actor, actor_exists=False)

    with pytest.raises(ActorNotFoundError):
        handler.handle(CreateOrganizationCommand(actor, "Acme"))

    assert uow.committed is False
    assert uow.rolled_back is True
    assert repo.tenants == []
    assert repo.memberships == []


def test_tenant_persist_failure_rolls_back() -> None:
    actor = uuid4()
    repo = FakeOrganizationRepository(fail_on_tenant=True)
    uow = FakeUnitOfWork(repo)
    handler = _handler(repository=repo, uow=uow, actor=actor)

    with pytest.raises(RuntimeError):
        handler.handle(CreateOrganizationCommand(actor, "Acme"))

    assert uow.committed is False
    assert uow.rolled_back is True
    assert repo.memberships == []


def test_membership_persist_failure_rolls_back() -> None:
    actor = uuid4()
    repo = FakeOrganizationRepository(fail_on_membership=True)
    uow = FakeUnitOfWork(repo)
    handler = _handler(repository=repo, uow=uow, actor=actor)

    with pytest.raises(RuntimeError):
        handler.handle(CreateOrganizationCommand(actor, "Acme"))

    assert uow.committed is False
    assert uow.rolled_back is True
    # Tenant eklenmiş olabilir ama commit edilmedi → rollback ile geri alınır.
