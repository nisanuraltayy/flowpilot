"""Blocked approval task listeleme + çözümleme use-case'leri (FP-E06-009).

owner/admin, self-approval nedeniyle blocked kalan approval adımlarını görür ve — rol ataması
düzeltildikten sonra — güvenli biçimde uygun kullanıcıya yeniden çözer. Bu, GENEL bir açık-task
reassignment sistemi DEĞİLDİR: yalnız `self_approval_no_eligible_assignee` ile blocked kalan
adım için çalışır. Aday, mevcut aktif approval_role_assignment'tan alınır (keyfi user_id ALINMAZ);
aktif üye olmalı ve talep sahibi OLMAMALIDIR. Değişiklik + audit AYNI transaction'da.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from flowpilot.modules.approval.application.blocked_task_dto import (
    BlockedApprovalTaskView,
    ResolveBlockedTaskCommand,
    ResolveBlockedTaskResult,
)
from flowpilot.modules.approval.application.blocked_task_errors import (
    BlockedTaskActorNotMemberError,
    BlockedTaskNotFoundError,
    BlockedTaskResolveConflictError,
)
from flowpilot.modules.approval.application.blocked_task_ports import (
    BlockedApprovalTaskListQuery,
    ResolveBlockedTaskUnitOfWork,
)
from flowpilot.modules.audit.application.dto import AuditEventType, AuditRecord
from flowpilot.modules.authorization.application.access import Permission, ensure_permitted
from flowpilot.modules.organization.application.contracts import MembershipQuery
from flowpilot.modules.purchase_request.application.approval_link import (
    resolve_purchase_request_id,
)
from flowpilot.modules.workflow_runtime.application.errors import (
    ConcurrencyConflictError,
    SelfApprovalForbiddenError,
    TaskNotBlockedError,
    WorkflowInstanceNotFoundError,
    WorkflowTaskNotFoundError,
)
from flowpilot.modules.workflow_runtime.application.port import WorkflowRuntimeTransactionPort
from flowpilot.shared.clock import ClockPort
from flowpilot.shared.ids import IdGeneratorPort

ResolveUnitOfWorkFactory = Callable[[], ResolveBlockedTaskUnitOfWork]

_AGGREGATE_PR = "purchase_request"
_SELF_APPROVAL_REASON = "self_approval_no_eligible_assignee"
_BLOCKED = "blocked"


class ListBlockedApprovalTasksHandler:
    """Blocked approval task'ları listeler (owner/admin; member → 403; non-member → 404)."""

    def __init__(
        self, *, list_query: BlockedApprovalTaskListQuery, membership_query: MembershipQuery
    ) -> None:
        self._query = list_query
        self._memberships = membership_query

    def handle(
        self, *, tenant_id: UUID, actor_user_id: UUID, limit: int
    ) -> list[BlockedApprovalTaskView]:
        actor = self._memberships.find_active(tenant_id=tenant_id, user_id=actor_user_id)
        if actor is None:
            raise BlockedTaskActorNotMemberError("aktif üyelik bulunamadı")
        ensure_permitted(role=actor.role, permission=Permission.APPROVAL_BLOCKED_TASK_READ)
        return self._query.list_blocked(tenant_id=tenant_id, limit=limit)


class ResolveBlockedApprovalTaskHandler:
    """Self-approval nedeniyle blocked adımı uygun kullanıcıya güvenli çözer (atomik)."""

    def __init__(
        self,
        *,
        unit_of_work_factory: ResolveUnitOfWorkFactory,
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

    def handle(self, command: ResolveBlockedTaskCommand) -> ResolveBlockedTaskResult:
        # 1) Coarse authz (owner/admin; member 403; non-member 404).
        actor = self._memberships.find_active(
            tenant_id=command.tenant_id, user_id=command.actor_user_id
        )
        if actor is None:
            raise BlockedTaskActorNotMemberError("aktif üyelik bulunamadı")
        ensure_permitted(role=actor.role, permission=Permission.APPROVAL_BLOCKED_TASK_RESOLVE)

        now = self._clock.now()
        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)

            # 2) Task aynı tenant scope'unda + self-approval nedeniyle blocked olmalı.
            try:
                task = uow.tasks.get(command.task_id)
            except WorkflowTaskNotFoundError as exc:
                raise BlockedTaskNotFoundError("task bulunamadı") from exc
            if task.status.value != _BLOCKED or task.blocked_reason != _SELF_APPROVAL_REASON:
                raise BlockedTaskResolveConflictError("task self-approval nedeniyle blocked değil")

            # 3) Aday YALNIZ mevcut aktif role assignment'tan alınır (keyfi user_id yok).
            candidate = uow.role_assignments.find_active_user(
                tenant_id=command.tenant_id, role_key=task.approver_role
            )
            if candidate is None:
                raise BlockedTaskResolveConflictError(
                    f"{task.approver_role} için aktif rol ataması yok — önce atama yapılmalı"
                )

            # 4) Aday aynı organizasyonda AKTİF üye olmalı (requester kontrolü runtime'da).
            if (
                self._memberships.find_active(tenant_id=command.tenant_id, user_id=candidate)
                is None
            ):
                raise BlockedTaskResolveConflictError("aday aktif üye değil — atanamaz")

            # 5) Runtime: FOR UPDATE + blocked/self-approval + requester!=aday + resolve.
            try:
                resolved = self._runtime.resolve_blocked_task_tx(
                    uow,
                    tenant_id=command.tenant_id,
                    task_id=command.task_id,
                    new_assignee_id=candidate,
                    now=now,
                )
            except (TaskNotBlockedError, SelfApprovalForbiddenError, ConcurrencyConflictError) as e:
                raise BlockedTaskResolveConflictError("çözümleme çakışması") from e
            except (WorkflowTaskNotFoundError, WorkflowInstanceNotFoundError) as exc:
                raise BlockedTaskNotFoundError("task bulunamadı") from exc

            pr_id = resolve_purchase_request_id(
                uow.purchase_requests, workflow_instance_id=resolved.instance_id
            )
            self._write_audit(uow, command, resolved, pr_id=pr_id, previous=task, now=now)
            uow.commit()

        return ResolveBlockedTaskResult(
            task_id=resolved.task_id,
            purchase_request_id=pr_id,
            approver_role=resolved.approver_role,
            status=resolved.status,
            assigned_user_id=resolved.assigned_user_id,
            version=resolved.version,
        )

    def _write_audit(
        self,
        uow: ResolveBlockedTaskUnitOfWork,
        command: ResolveBlockedTaskCommand,
        resolved: object,
        *,
        pr_id: UUID | None,
        previous: object,
        now: datetime,
    ) -> None:
        assigned = resolved.assigned_user_id  # type: ignore[attr-defined]
        uow.audit.append(
            AuditRecord(
                event_id=self._ids.new_uuid(),
                tenant_id=command.tenant_id,
                aggregate_type=_AGGREGATE_PR,
                aggregate_id=pr_id if pr_id is not None else command.task_id,
                event_type=AuditEventType.APPROVAL_TASK_ASSIGNMENT_RESOLVED,
                occurred_at=now,
                actor_user_id=command.actor_user_id,
                role_key=resolved.approver_role,  # type: ignore[attr-defined]
                task_id=command.task_id,
                metadata={
                    "new_assigned_user_id": str(assigned),
                    "approver_role": resolved.approver_role,  # type: ignore[attr-defined]
                    "new_version": resolved.version,  # type: ignore[attr-defined]
                },
            )
        )
