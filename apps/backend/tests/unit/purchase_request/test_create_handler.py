"""CreatePurchaseRequestHandler use-case davranışı (fake port'larla; DB YOK)."""

from __future__ import annotations

from types import TracebackType
from uuid import UUID, uuid4

import pytest

from flowpilot.modules.organization.application.contracts import ActiveMembershipView
from flowpilot.modules.purchase_request.application.create_handler import (
    CreatePurchaseRequestHandler,
)
from flowpilot.modules.purchase_request.application.dto import CreatePurchaseRequestCommand
from flowpilot.modules.purchase_request.application.errors import (
    FirstApprovalTaskMissingError,
    MembershipNotActiveError,
    WorkflowConfigurationError,
)
from flowpilot.modules.purchase_request.domain.purchase_request import PurchaseRequest
from flowpilot.modules.workflow_runtime.application.dto import (
    InstanceView,
    PublishDefinitionCommand,
    PublishDefinitionResult,
    StartInstanceCommand,
    SubmitFormCommand,
    TaskView,
)
from flowpilot.modules.workflow_runtime.application.port import WorkflowUnitOfWork
from flowpilot.modules.workflow_runtime.domain.errors import WorkflowRuntimeError
from tests.unit.fakes import FakeClock, FakeIdGenerator

TENANT = uuid4()
ACTOR = uuid4()
VERSION_ID = uuid4()
INSTANCE_ID = uuid4()


class FakeMembershipQuery:
    def __init__(self, *, active: bool) -> None:
        self._active = active

    def find_active(self, *, tenant_id: UUID, user_id: UUID) -> ActiveMembershipView | None:
        if not self._active:
            return None
        return ActiveMembershipView(
            membership_id=uuid4(), tenant_id=tenant_id, user_id=user_id, role="owner"
        )


class FakeProvisioning:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.calls: list[PublishDefinitionCommand] = []

    def ensure_published_definition(
        self, command: PublishDefinitionCommand
    ) -> PublishDefinitionResult:
        self.calls.append(command)
        if self._fail:
            raise WorkflowRuntimeError("provision failure")
        return PublishDefinitionResult(
            definition_id=uuid4(),
            definition_version_id=VERSION_ID,
            version_no=1,
            content_hash="h",
        )


class FakeRuntimeTx:
    def __init__(self, *, first_task_role: str | None = "team_manager") -> None:
        self._role = first_task_role
        self.start_commands: list[StartInstanceCommand] = []
        self.submit_commands: list[SubmitFormCommand] = []

    def start_instance_tx(
        self, uow: WorkflowUnitOfWork, command: StartInstanceCommand
    ) -> InstanceView:
        self.start_commands.append(command)
        return InstanceView(
            instance_id=INSTANCE_ID,
            definition_version_id=command.definition_version_id,
            definition_hash="h",
            status="waiting",
            current_node_id="purchase_form",
            version=1,
        )

    def submit_form_tx(self, uow: WorkflowUnitOfWork, command: SubmitFormCommand) -> InstanceView:
        self.submit_commands.append(command)
        task = (
            TaskView(
                task_id=uuid4(),
                node_id="approval",
                step_index=0,
                approver_role=self._role,
                status="active",
            )
            if self._role is not None
            else None
        )
        return InstanceView(
            instance_id=command.instance_id,
            definition_version_id=VERSION_ID,
            definition_hash="h",
            status="waiting",
            current_node_id="approval",
            version=command.expected_version + 1,
            active_task=task,
        )


class FakePurchaseRequestRepo:
    def __init__(self) -> None:
        self.added: list[PurchaseRequest] = []
        self.updated: list[PurchaseRequest] = []

    def add(self, request: PurchaseRequest) -> None:
        self.added.append(request)

    def update_checked(self, request: PurchaseRequest, *, expected_version: int) -> None:
        self.updated.append(request)


class FakeComposedUoW:
    def __init__(self, repo: FakePurchaseRequestRepo) -> None:
        self.purchase_requests = repo
        self.committed = False
        self.rolled_back = False
        self.tenant_context: UUID | None = None
        self.actor_context: UUID | None = None

    def __enter__(self) -> FakeComposedUoW:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rolled_back = True

    def set_actor_context(self, actor_user_id: UUID) -> None:
        self.actor_context = actor_user_id

    def set_tenant_context(self, tenant_id: UUID) -> None:
        self.tenant_context = tenant_id

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _command(amount: int = 1_250_000) -> CreatePurchaseRequestCommand:
    return CreatePurchaseRequestCommand(
        actor_user_id=ACTOR,
        tenant_id=TENANT,
        title="Yeni dizüstü",
        description="ekip için",
        amount_minor=amount,
        currency="TRY",
    )


def _handler(
    *,
    uow: FakeComposedUoW,
    membership: FakeMembershipQuery,
    provisioning: FakeProvisioning,
    runtime: FakeRuntimeTx,
) -> CreatePurchaseRequestHandler:
    return CreatePurchaseRequestHandler(
        unit_of_work_factory=lambda: uow,  # type: ignore[arg-type]
        membership_query=membership,
        provisioning=provisioning,
        runtime=runtime,  # type: ignore[arg-type]
        clock=FakeClock(
            __import__("datetime").datetime(2026, 7, 19, tzinfo=__import__("datetime").UTC)
        ),
        id_generator=FakeIdGenerator([uuid4() for _ in range(10)]),
    )


def test_happy_path_commits_and_calls_runtime() -> None:
    repo = FakePurchaseRequestRepo()
    uow = FakeComposedUoW(repo)
    provisioning = FakeProvisioning()
    runtime = FakeRuntimeTx(first_task_role="team_manager")
    handler = _handler(
        uow=uow,
        membership=FakeMembershipQuery(active=True),
        provisioning=provisioning,
        runtime=runtime,
    )

    result = handler.handle(_command())

    assert uow.committed is True
    assert uow.tenant_context == TENANT
    assert result.workflow_instance_id == INSTANCE_ID
    assert result.status == "in_approval"
    assert result.current_approval_role == "team_manager"
    # Runtime doğru payload ile çağrıldı.
    assert runtime.start_commands[0].definition_version_id == VERSION_ID
    assert runtime.submit_commands[0].form_data["amount_minor"] == 1_250_000
    assert runtime.submit_commands[0].form_data["currency"] == "TRY"
    # PR insert + workflow bağlama update.
    assert len(repo.added) == 1
    assert len(repo.updated) == 1


def test_inactive_membership_rejected_before_any_write() -> None:
    repo = FakePurchaseRequestRepo()
    uow = FakeComposedUoW(repo)
    handler = _handler(
        uow=uow,
        membership=FakeMembershipQuery(active=False),
        provisioning=FakeProvisioning(),
        runtime=FakeRuntimeTx(),
    )
    with pytest.raises(MembershipNotActiveError):
        handler.handle(_command())
    assert uow.committed is False
    assert repo.added == []


def test_provisioning_failure_maps_to_workflow_configuration_error() -> None:
    uow = FakeComposedUoW(FakePurchaseRequestRepo())
    handler = _handler(
        uow=uow,
        membership=FakeMembershipQuery(active=True),
        provisioning=FakeProvisioning(fail=True),
        runtime=FakeRuntimeTx(),
    )
    with pytest.raises(WorkflowConfigurationError):
        handler.handle(_command())
    assert uow.committed is False


def test_missing_first_task_rolls_back() -> None:
    repo = FakePurchaseRequestRepo()
    uow = FakeComposedUoW(repo)
    handler = _handler(
        uow=uow,
        membership=FakeMembershipQuery(active=True),
        provisioning=FakeProvisioning(),
        runtime=FakeRuntimeTx(first_task_role=None),  # ilk task oluşmadı
    )
    with pytest.raises(FirstApprovalTaskMissingError):
        handler.handle(_command())
    assert uow.committed is False
    assert uow.rolled_back is True  # __exit__ rollback


def test_invalid_amount_rejected_before_membership() -> None:
    from flowpilot.modules.purchase_request.application.errors import InvalidMoneyError

    repo = FakePurchaseRequestRepo()
    uow = FakeComposedUoW(repo)
    membership = FakeMembershipQuery(active=True)
    handler = _handler(
        uow=uow, membership=membership, provisioning=FakeProvisioning(), runtime=FakeRuntimeTx()
    )
    with pytest.raises(InvalidMoneyError):
        handler.handle(_command(amount=0))
    assert repo.added == []
