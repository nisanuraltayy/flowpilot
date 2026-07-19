"""DecideApprovalTask use-case — cross-module ATOMİK onay kararı.

Tek transaction: runtime task transition + sonraki task + Purchase Request status +
ApprovalDecision (append-only) + runtime event/outbox + audit entry'leri. Commit
başarısızsa hiçbir kısmi state kalmaz. Yetki `assigned_user_id` iledir (owner #6);
self-approval MVP'de SERBEST (owner #7, [[ASM-0016]]). Idempotency: aynı key replay →
aynı sonuç; farklı payload/task → conflict. Concurrent iki karar → tek kazanan.
Infrastructure/SQL hata detayı HTTP'ye sızmaz (application error'a çevrilir).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from flowpilot.modules.approval.application.dto import (
    DecideApprovalTaskCommand,
    DecideApprovalTaskResult,
)
from flowpilot.modules.approval.application.errors import (
    ApprovalMembershipNotActiveError,
    ApprovalTaskNotAssignedError,
    DuplicateDecisionConflictError,
    InvalidApprovalDecisionError,
)
from flowpilot.modules.approval.application.ports import ApprovalDecisionUnitOfWork
from flowpilot.modules.approval.domain.enums import ApprovalDecisionType
from flowpilot.modules.approval.domain.models import (
    ApprovalComment,
    ApprovalDecision,
    ApprovalDecisionId,
)
from flowpilot.modules.audit.application.dto import AuditEventType, AuditRecord
from flowpilot.modules.organization.application.contracts import MembershipQuery
from flowpilot.modules.purchase_request.application.approval_link import (
    apply_workflow_outcome,
    resolve_purchase_request_id,
)
from flowpilot.modules.workflow_runtime.application.dto import DecisionResult
from flowpilot.modules.workflow_runtime.application.errors import (
    ConcurrencyConflictError,
    DuplicateDecisionError,
    InvalidTransitionError,
    SequenceOrderError,
    TerminalInstanceError,
    UnauthorizedApproverError,
    WorkflowInstanceNotFoundError,
    WorkflowTaskNotFoundError,
)
from flowpilot.modules.workflow_runtime.application.port import WorkflowRuntimeTransactionPort
from flowpilot.shared.clock import ClockPort
from flowpilot.shared.identifiers import TenantId, UserId
from flowpilot.shared.ids import IdGeneratorPort

UnitOfWorkFactory = Callable[[], ApprovalDecisionUnitOfWork]

_DECISION_TO_RUNTIME = {"approve": "approved", "reject": "rejected"}
_AGGREGATE_PR = "purchase_request"

_NOT_FOUND = (WorkflowTaskNotFoundError, WorkflowInstanceNotFoundError, UnauthorizedApproverError)
# Zaten kararlaştırılmış / terminal / sıra dışı → tek geçerli karar (409). TerminalInstance
# ve InvalidTransition, nihai adım farklı key ile tekrar denendiğinde buraya düşer.
_CONFLICT = (
    DuplicateDecisionError,
    ConcurrencyConflictError,
    SequenceOrderError,
    TerminalInstanceError,
    InvalidTransitionError,
)


class DecideApprovalTaskHandler:
    """Onay kararı atomik use-case'i."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        membership_query: MembershipQuery,
        runtime: WorkflowRuntimeTransactionPort,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._memberships = membership_query
        self._runtime = runtime
        self._clock = clock
        self._ids = id_generator

    def handle(self, command: DecideApprovalTaskCommand) -> DecideApprovalTaskResult:
        runtime_decision = _DECISION_TO_RUNTIME.get(command.decision)
        if runtime_decision is None:
            raise InvalidApprovalDecisionError(f"geçersiz karar: {command.decision!r}")
        comment = ApprovalComment(command.comment)
        decision_type = ApprovalDecisionType(command.decision)

        if (
            self._memberships.find_active(
                tenant_id=command.tenant_id, user_id=command.actor_user_id
            )
            is None
        ):
            raise ApprovalMembershipNotActiveError("aktif üyelik bulunamadı")

        now = self._clock.now()
        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)

            try:
                decision = self._runtime.decide_task_tx(
                    uow,
                    tenant_id=command.tenant_id,
                    actor_user_id=command.actor_user_id,
                    task_id=command.task_id,
                    decision=runtime_decision,
                    idempotency_key=command.idempotency_key,
                )
            except _NOT_FOUND as exc:
                raise ApprovalTaskNotAssignedError("task bulunamadı veya atanmamış") from exc
            except _CONFLICT as exc:
                raise DuplicateDecisionConflictError("karar çakışması") from exc

            # PR id'sini transition YAPMADAN çöz (duplicate-replay yolu için de gerekli).
            pr_id = (
                resolve_purchase_request_id(
                    uow.purchase_requests, workflow_instance_id=decision.instance_id
                )
                or decision.instance_id
            )

            if decision.duplicate:
                existing = uow.approval_decisions.find_by_task(task_id=command.task_id)
                uow.rollback()
                if existing is None or existing.idempotency_key != command.idempotency_key:
                    raise DuplicateDecisionConflictError("aynı task için farklı karar/anahtar")
                return self._result(
                    command, decision, pr_id=pr_id, decided_at=existing.created_at, duplicate=True
                )

            inserted = uow.approval_decisions.add_if_absent(
                ApprovalDecision(
                    id=ApprovalDecisionId(self._ids.new_uuid()),
                    tenant_id=TenantId(command.tenant_id),
                    task_id=command.task_id,
                    actor_user_id=UserId(command.actor_user_id),
                    decision=decision_type,
                    comment=comment,
                    idempotency_key=command.idempotency_key,
                    request_fingerprint=_fingerprint(command, runtime_decision),
                    created_at=now,
                )
            )
            if not inserted:
                raise DuplicateDecisionConflictError("karar zaten kaydedilmiş")

            # PR status geçişi PR application'ında (domain transition orada kalır).
            outcome = apply_workflow_outcome(
                uow.purchase_requests,
                workflow_instance_id=decision.instance_id,
                workflow_status=decision.instance_status,
                now=now,
            )
            self._write_audit(uow, command, decision, aggregate_id=pr_id, now=now)
            uow.commit()

        return self._result(
            command,
            decision,
            pr_id=pr_id,
            decided_at=now,
            duplicate=False,
            pr_status=outcome.status,
        )

    def _write_audit(
        self,
        uow: ApprovalDecisionUnitOfWork,
        command: DecideApprovalTaskCommand,
        decision: DecisionResult,
        *,
        aggregate_id: UUID,
        now: datetime,
    ) -> None:
        def entry(event: AuditEventType, *, role: str | None, task: UUID | None) -> AuditRecord:
            return AuditRecord(
                event_id=self._ids.new_uuid(),
                tenant_id=command.tenant_id,
                aggregate_type=_AGGREGATE_PR,
                aggregate_id=aggregate_id,
                event_type=event,
                occurred_at=now,
                actor_user_id=command.actor_user_id,
                role_key=role,
                task_id=task,
                metadata={"decision": command.decision, "status": decision.instance_status},
            )

        approved = command.decision == "approve"
        uow.audit.append(
            entry(
                AuditEventType.APPROVAL_APPROVED if approved else AuditEventType.APPROVAL_REJECTED,
                role=decision.required_role,
                task=command.task_id,
            )
        )
        if approved and decision.next_approval_role is not None:
            uow.audit.append(
                entry(
                    AuditEventType.APPROVAL_TASK_ASSIGNED,
                    role=decision.next_approval_role,
                    task=decision.activated_task_id,
                )
            )
        if decision.instance_status == "completed":
            uow.audit.append(entry(AuditEventType.WORKFLOW_COMPLETED, role=None, task=None))
        elif decision.instance_status == "rejected":
            uow.audit.append(entry(AuditEventType.WORKFLOW_REJECTED, role=None, task=None))

    def _result(
        self,
        command: DecideApprovalTaskCommand,
        decision: DecisionResult,
        *,
        pr_id: UUID,
        decided_at: datetime,
        duplicate: bool,
        pr_status: str | None = None,
    ) -> DecideApprovalTaskResult:
        return DecideApprovalTaskResult(
            task_id=command.task_id,
            decision="approved" if command.decision == "approve" else "rejected",
            purchase_request_id=pr_id,
            purchase_request_status=pr_status or _pr_status_from_instance(decision.instance_status),
            workflow_status=decision.instance_status,
            next_approval_role=decision.next_approval_role,
            decided_at=decided_at,
            duplicate=duplicate,
        )


def _fingerprint(command: DecideApprovalTaskCommand, runtime_decision: str) -> str:
    raw = f"{command.task_id}|{runtime_decision}|{command.comment or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _pr_status_from_instance(instance_status: str) -> str:
    if instance_status == "completed":
        return "approved"
    if instance_status == "rejected":
        return "rejected"
    return "in_approval"
