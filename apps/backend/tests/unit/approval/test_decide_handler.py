"""DecideApprovalTaskHandler use-case davranışı (fake port'larla; DB YOK).

Kapsam: ara/nihai approve, reject, self-approval SERBEST (owner #7), yetkisiz assignee
reddi, idempotent replay, duplicate conflict, membership reddi, geçersiz karar.
Atomiklik (tek transaction) burada FAKE uow ile; gerçek DB atomikliği integration'da.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from flowpilot.modules.approval.application.decide_handler import DecideApprovalTaskHandler
from flowpilot.modules.approval.application.dto import DecideApprovalTaskCommand
from flowpilot.modules.approval.application.errors import (
    ApprovalMembershipNotActiveError,
    ApprovalTaskNotAssignedError,
    DuplicateDecisionConflictError,
    InvalidApprovalDecisionError,
)
from flowpilot.modules.approval.domain.enums import ApprovalDecisionType
from flowpilot.modules.approval.domain.models import (
    ApprovalComment,
    ApprovalDecision,
    ApprovalDecisionId,
)
from flowpilot.modules.audit.application.dto import AuditRecord
from flowpilot.modules.organization.application.contracts import ActiveMembershipView
from flowpilot.modules.purchase_request.domain.identifiers import PurchaseRequestId
from flowpilot.modules.purchase_request.domain.money import Money
from flowpilot.modules.purchase_request.domain.purchase_request import PurchaseRequest
from flowpilot.modules.purchase_request.domain.value_objects import (
    PurchaseRequestDescription,
    PurchaseRequestTitle,
)
from flowpilot.modules.workflow_runtime.application.dto import DecisionResult
from flowpilot.modules.workflow_runtime.application.errors import (
    DuplicateDecisionError,
    UnauthorizedApproverError,
)
from flowpilot.modules.workflow_runtime.application.port import WorkflowUnitOfWork
from flowpilot.shared.identifiers import TenantId, UserId
from tests.unit.fakes import FakeClock, FakeIdGenerator

TENANT = uuid4()
ACTOR = uuid4()
TASK = uuid4()
INSTANCE = uuid4()
_NOW = datetime(2026, 7, 19, tzinfo=UTC)


def _pr_in_approval(requested_by: UUID) -> PurchaseRequest:
    pr, _ = PurchaseRequest.create(
        id=PurchaseRequestId(uuid4()),
        tenant_id=TenantId(TENANT),
        requested_by=UserId(requested_by),
        title=PurchaseRequestTitle("Dizüstü"),
        description=PurchaseRequestDescription(None),
        money=Money(amount_minor=1_250_000, currency="TRY"),
        created_at=_NOW,
    )
    return pr.attach_workflow(workflow_instance_id=INSTANCE, now=_NOW)


class FakeMembershipQuery:
    def __init__(self, *, active: bool = True) -> None:
        self._active = active

    def find_active(self, *, tenant_id: UUID, user_id: UUID) -> ActiveMembershipView | None:
        if not self._active:
            return None
        return ActiveMembershipView(
            membership_id=uuid4(), tenant_id=tenant_id, user_id=user_id, role="owner"
        )

    def find_active_owner(self, *, tenant_id: UUID) -> ActiveMembershipView | None:
        return None


class FakeRuntime:
    """`decide_task_tx`'i yapılandırılmış DecisionResult ya da hata ile taklit eder."""

    def __init__(self, result: DecisionResult | None = None, *, raises: Exception | None = None):
        self._result = result
        self._raises = raises
        self.calls: list[dict[str, object]] = []

    def decide_task_tx(
        self,
        uow: WorkflowUnitOfWork,
        *,
        tenant_id: UUID,
        actor_user_id: UUID,
        task_id: UUID,
        decision: str,
        idempotency_key: str,
        approver_role: str | None = None,
    ) -> DecisionResult:
        self.calls.append({"task_id": task_id, "decision": decision, "key": idempotency_key})
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result


class FakePRRepo:
    def __init__(self, pr: PurchaseRequest | None) -> None:
        self._pr = pr
        self.updated: list[PurchaseRequest] = []

    def get_by_workflow_instance(self, workflow_instance_id: UUID) -> PurchaseRequest | None:
        return self._pr

    def update_checked(self, request: PurchaseRequest, *, expected_version: int) -> None:
        self.updated.append(request)
        self._pr = request


class FakeDecisionRepo:
    def __init__(self, *, existing: ApprovalDecision | None = None, insert_ok: bool = True) -> None:
        self._existing = existing
        self._insert_ok = insert_ok
        self.inserted: list[ApprovalDecision] = []

    def add_if_absent(self, decision: ApprovalDecision) -> bool:
        if not self._insert_ok:
            return False
        self.inserted.append(decision)
        self._existing = decision
        return True

    def find_by_task(self, *, task_id: UUID) -> ApprovalDecision | None:
        return self._existing


class FakeAuditWriter:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        self.records.append(record)


class FakeUoW:
    def __init__(self, pr: PurchaseRequest | None, decisions: FakeDecisionRepo) -> None:
        self.purchase_requests = FakePRRepo(pr)
        self.approval_decisions = decisions
        self.audit = FakeAuditWriter()
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> FakeUoW:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rolled_back = True

    def set_actor_context(self, actor_user_id: UUID) -> None: ...
    def set_tenant_context(self, tenant_id: UUID) -> None: ...

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _handler(
    uow: FakeUoW, runtime: FakeRuntime, *, membership_active: bool = True
) -> DecideApprovalTaskHandler:
    return DecideApprovalTaskHandler(
        unit_of_work_factory=lambda: uow,  # type: ignore[arg-type]
        membership_query=FakeMembershipQuery(active=membership_active),
        runtime=runtime,  # type: ignore[arg-type]
        clock=FakeClock(_NOW),
        id_generator=FakeIdGenerator([uuid4() for _ in range(20)]),
    )


def _cmd(
    *, decision: str = "approve", key: str = "idem-1", actor: UUID = ACTOR
) -> DecideApprovalTaskCommand:
    return DecideApprovalTaskCommand(
        tenant_id=TENANT,
        actor_user_id=actor,
        task_id=TASK,
        decision=decision,
        comment="uygundur",
        idempotency_key=key,
    )


def _decision(
    *,
    status: str,
    duplicate: bool = False,
    next_role: str | None = None,
    activated: UUID | None = None,
) -> DecisionResult:
    return DecisionResult(
        task_id=TASK,
        step_index=0,
        instance_id=INSTANCE,
        decision="approved",
        duplicate=duplicate,
        instance_status=status,
        activated_task_id=activated,
        required_role="team_manager",
        next_approval_role=next_role,
        next_task_assigned_user_id=None,
    )


def test_intermediate_approve_keeps_pr_in_approval_and_audits_next_assignment() -> None:
    pr = _pr_in_approval(requested_by=uuid4())
    uow = FakeUoW(pr, FakeDecisionRepo())
    runtime = FakeRuntime(_decision(status="running", next_role="finance", activated=uuid4()))
    result = _handler(uow, runtime).handle(_cmd())

    assert uow.committed is True
    assert result.purchase_request_status == "in_approval"
    assert result.next_approval_role == "finance"
    assert uow.purchase_requests.updated == []  # ara adımda PR status değişmez
    events = [r.event_type.value for r in uow.audit.records]
    assert "approval.approved" in events
    assert "approval.task_assigned" in events  # sonraki adım atandı


def test_final_approve_sets_pr_approved_and_completed_audit() -> None:
    pr = _pr_in_approval(requested_by=uuid4())
    uow = FakeUoW(pr, FakeDecisionRepo())
    runtime = FakeRuntime(_decision(status="completed"))
    result = _handler(uow, runtime).handle(_cmd())

    assert result.purchase_request_status == "approved"
    assert result.workflow_status == "completed"
    assert len(uow.purchase_requests.updated) == 1
    assert uow.purchase_requests.updated[0].status.value == "approved"
    assert "workflow.completed" in [r.event_type.value for r in uow.audit.records]


def test_reject_sets_pr_rejected() -> None:
    pr = _pr_in_approval(requested_by=uuid4())
    uow = FakeUoW(pr, FakeDecisionRepo())
    runtime = FakeRuntime(_decision(status="rejected"))
    result = _handler(uow, runtime).handle(_cmd(decision="reject"))

    assert result.purchase_request_status == "rejected"
    assert uow.purchase_requests.updated[0].status.value == "rejected"
    assert "workflow.rejected" in [r.event_type.value for r in uow.audit.records]


def test_self_approval_is_allowed_owner_decision_asm_0016() -> None:
    # Requester == approver: MVP'de SERBEST (owner #7). Özel blok YOK.
    pr = _pr_in_approval(requested_by=ACTOR)
    uow = FakeUoW(pr, FakeDecisionRepo())
    runtime = FakeRuntime(_decision(status="completed"))
    result = _handler(uow, runtime).handle(_cmd(actor=ACTOR))

    assert uow.committed is True
    assert result.purchase_request_status == "approved"


def test_unauthorized_assignee_maps_to_not_assigned_and_rolls_back() -> None:
    pr = _pr_in_approval(requested_by=uuid4())
    uow = FakeUoW(pr, FakeDecisionRepo())
    runtime = FakeRuntime(raises=UnauthorizedApproverError("başkası"))
    with pytest.raises(ApprovalTaskNotAssignedError):
        _handler(uow, runtime).handle(_cmd())
    assert uow.committed is False


def test_membership_inactive_rejected_before_runtime() -> None:
    pr = _pr_in_approval(requested_by=uuid4())
    uow = FakeUoW(pr, FakeDecisionRepo())
    runtime = FakeRuntime(_decision(status="completed"))
    with pytest.raises(ApprovalMembershipNotActiveError):
        _handler(uow, runtime, membership_active=False).handle(_cmd())
    assert runtime.calls == []  # runtime hiç çağrılmadı


def test_invalid_decision_value_rejected() -> None:
    pr = _pr_in_approval(requested_by=uuid4())
    uow = FakeUoW(pr, FakeDecisionRepo())
    runtime = FakeRuntime(_decision(status="completed"))
    with pytest.raises(InvalidApprovalDecisionError):
        _handler(uow, runtime).handle(_cmd(decision="maybe"))


def test_idempotent_replay_same_key_returns_same_result_without_new_decision() -> None:
    pr = _pr_in_approval(requested_by=uuid4())
    existing = ApprovalDecision(
        id=ApprovalDecisionId(uuid4()),
        tenant_id=TenantId(TENANT),
        task_id=TASK,
        actor_user_id=UserId(ACTOR),
        decision=ApprovalDecisionType.APPROVE,
        comment=ApprovalComment("uygundur"),
        idempotency_key="idem-1",
        request_fingerprint="fp",
        created_at=_NOW,
    )
    decisions = FakeDecisionRepo(existing=existing)
    uow = FakeUoW(pr, decisions)
    runtime = FakeRuntime(_decision(status="completed", duplicate=True))
    result = _handler(uow, runtime).handle(_cmd(key="idem-1"))

    assert result.duplicate is True
    assert uow.committed is False
    assert uow.rolled_back is True
    assert decisions.inserted == []  # yeni karar yazılmadı


def test_duplicate_with_different_key_conflicts() -> None:
    pr = _pr_in_approval(requested_by=uuid4())
    existing = ApprovalDecision(
        id=ApprovalDecisionId(uuid4()),
        tenant_id=TenantId(TENANT),
        task_id=TASK,
        actor_user_id=UserId(ACTOR),
        decision=ApprovalDecisionType.APPROVE,
        comment=ApprovalComment(None),
        idempotency_key="original-key",
        request_fingerprint="fp",
        created_at=_NOW,
    )
    uow = FakeUoW(pr, FakeDecisionRepo(existing=existing))
    runtime = FakeRuntime(_decision(status="completed", duplicate=True))
    with pytest.raises(DuplicateDecisionConflictError):
        _handler(uow, runtime).handle(_cmd(key="different-key"))


def test_runtime_duplicate_error_maps_to_conflict() -> None:
    pr = _pr_in_approval(requested_by=uuid4())
    uow = FakeUoW(pr, FakeDecisionRepo())
    runtime = FakeRuntime(raises=DuplicateDecisionError("çakışma"))
    with pytest.raises(DuplicateDecisionConflictError):
        _handler(uow, runtime).handle(_cmd())
    assert uow.committed is False
