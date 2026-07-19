"""WorkflowRuntimeService — `WorkflowRuntimePort`'un use-case orkestrasyonu.

Yalnız port'lara (repository, UnitOfWork, Clock, IdGenerator) bağımlıdır; SQL veya
ORM görmez. Transaction sınırı UnitOfWork tarafından yönetilir: state + task +
event + outbox AYNI transaction'da yazılır (SPK-11). Her okuma/yazma tenant
context altında yapılır (RLS — SPK-10). Terminal guard, sıra ve duplicate
kontrolleri domain aggregate'lerindedir; hepsi bu servisten geçer.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from flowpilot.modules.workflow_runtime.application.dto import (
    CancelInstanceCommand,
    DecideTaskCommand,
    DecisionResult,
    DispatchStats,
    InstanceView,
    PublishDefinitionCommand,
    PublishDefinitionResult,
    ScheduleTimerCommand,
    StartInstanceCommand,
    SubmitFormCommand,
    TaskView,
    TimelineEntry,
)
from flowpilot.modules.workflow_runtime.application.port import (
    ClaimedOutboxEvent,
    WorkflowUnitOfWork,
)
from flowpilot.modules.workflow_runtime.domain import conditions
from flowpilot.modules.workflow_runtime.domain.definition import WorkflowDefinitionVersion
from flowpilot.modules.workflow_runtime.domain.enums import (
    WorkflowInstanceStatus,
    WorkflowNodeType,
    WorkflowTaskStatus,
)
from flowpilot.modules.workflow_runtime.domain.errors import (
    DefinitionValidationError,
    DuplicateDecisionError,
    InvalidTransitionError,
)
from flowpilot.modules.workflow_runtime.domain.event import IntegrationEvent, WorkflowEvent
from flowpilot.modules.workflow_runtime.domain.identifiers import (
    WorkflowDefinitionId,
    WorkflowDefinitionVersionId,
    WorkflowEventId,
    WorkflowInstanceId,
    WorkflowTaskId,
)
from flowpilot.modules.workflow_runtime.domain.instance import WorkflowInstance
from flowpilot.modules.workflow_runtime.domain.task import WorkflowTask
from flowpilot.shared.clock import ClockPort
from flowpilot.shared.identifiers import TenantId, UserId
from flowpilot.shared.ids import IdGeneratorPort

UnitOfWorkFactory = Callable[[], WorkflowUnitOfWork]

_DECISION_TO_STATUS = {
    "approved": WorkflowTaskStatus.APPROVED,
    "rejected": WorkflowTaskStatus.REJECTED,
}


class WorkflowRuntimeService:
    """`WorkflowRuntimePort` implementasyonu (composition root'ta wire edilir)."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._clock = clock
        self._ids = id_generator

    # ------------------------------------------------------------ publish

    def publish_definition(self, command: PublishDefinitionCommand) -> PublishDefinitionResult:
        now = self._clock.now()
        definition_version = WorkflowDefinitionVersion.publish(
            id=WorkflowDefinitionVersionId(self._ids.new_uuid()),
            definition_id=WorkflowDefinitionId(self._ids.new_uuid()),
            version_no=1,
            definition=command.definition,
        )
        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)
            definition_id = uow.definitions.ensure_definition(
                tenant_id=command.tenant_id,
                definition_id=definition_version.definition_id.value,
                definition_key=command.definition_key,
                created_at=now,
            )
            version = definition_version
            if definition_id != definition_version.definition_id.value:
                version = WorkflowDefinitionVersion(
                    id=definition_version.id,
                    definition_id=WorkflowDefinitionId(definition_id),
                    version_no=definition_version.version_no,
                    definition=definition_version.definition,
                    content_hash=definition_version.content_hash,
                )
            uow.definitions.add_version(version, tenant_id=command.tenant_id, published_at=now)
            uow.commit()
        return PublishDefinitionResult(
            definition_id=version.definition_id.value,
            definition_version_id=version.id.value,
            version_no=version.version_no,
            content_hash=version.content_hash,
        )

    # ------------------------------------------------------- provisioning

    def ensure_published_definition(
        self, command: PublishDefinitionCommand
    ) -> PublishDefinitionResult:
        """Idempotent + concurrent-safe provisioning (visual designer/endpoint yok).

        Mevcut published version varsa yeniden kullanır; aynı key/version farklı hash
        ile SESSİZCE OVERWRITE edilmez (DefinitionValidationError). version_no = 1.
        """
        version_no = 1
        candidate = WorkflowDefinitionVersion.publish(
            id=WorkflowDefinitionVersionId(self._ids.new_uuid()),
            definition_id=WorkflowDefinitionId(self._ids.new_uuid()),
            version_no=version_no,
            definition=command.definition,
        )
        now = self._clock.now()
        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)
            existing = uow.definitions.find_published_version(
                definition_key=command.definition_key, version_no=version_no
            )
            if existing is not None:
                self._assert_same_hash(existing, candidate)
                uow.rollback()
                return _version_result(existing)

            definition_id = uow.definitions.ensure_definition(
                tenant_id=command.tenant_id,
                definition_id=candidate.definition_id.value,
                definition_key=command.definition_key,
                created_at=now,
            )
            to_publish = WorkflowDefinitionVersion(
                id=candidate.id,
                definition_id=WorkflowDefinitionId(definition_id),
                version_no=version_no,
                definition=candidate.definition,
                content_hash=candidate.content_hash,
            )
            uow.definitions.add_version_if_absent(
                to_publish, tenant_id=command.tenant_id, published_at=now
            )
            stored = uow.definitions.find_published_version(
                definition_key=command.definition_key, version_no=version_no
            )
            if stored is None:  # yalnız RLS/görünürlük anomalisinde
                raise DefinitionValidationError("provisioning sonrası version okunamadı")
            self._assert_same_hash(stored, candidate)
            uow.commit()
        return _version_result(stored)

    @staticmethod
    def _assert_same_hash(
        stored: WorkflowDefinitionVersion, candidate: WorkflowDefinitionVersion
    ) -> None:
        if stored.content_hash != candidate.content_hash:
            raise DefinitionValidationError(
                "aynı key/version farklı içerik hash'i ile yayınlanamaz (silent overwrite yok)"
            )

    # ------------------------------------------------------------ start

    def start_instance(self, command: StartInstanceCommand) -> InstanceView:
        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)
            view = self.start_instance_tx(uow, command)
            uow.commit()
        return view

    def start_instance_tx(
        self, uow: WorkflowUnitOfWork, command: StartInstanceCommand
    ) -> InstanceView:
        """Instance başlatma domain işi — SAĞLANAN uow üzerinde, COMMIT ETMEZ.

        Context çağıran tarafından set edilir (cross-module compose transaction).
        """
        now = self._clock.now()
        tenant = TenantId(command.tenant_id)
        version = uow.definitions.get_version(command.definition_version_id)
        start_node = version.start_node()
        form_node_id = str(start_node["next"])

        instance = WorkflowInstance(
            id=WorkflowInstanceId(self._ids.new_uuid()),
            tenant_id=tenant,
            definition_version_id=version.id,
            definition_hash=version.content_hash,
            status=WorkflowInstanceStatus.WAITING,
            current_node_id=form_node_id,
            context={**command.initial_context, "requester_id": str(command.actor_user_id)},
            version=1,
        )
        uow.instances.add(instance, now=now)
        self._append_event(
            uow,
            tenant=tenant,
            instance_id=instance.id,
            event_type="instance.started",
            node_id=str(start_node["id"]),
            actor_type="user",
            now=now,
            detail={"definition_version_id": str(version.id.value)},
        )
        self._enqueue(
            uow,
            tenant=tenant,
            event_type="instance.started.v1",
            payload={"instance_id": str(instance.id.value), "tenant_id": str(tenant.value)},
            now=now,
        )
        return self._view(instance, active_task=None)

    # ------------------------------------------------------------ submit form

    def submit_form(self, command: SubmitFormCommand) -> InstanceView:
        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)
            view = self.submit_form_tx(uow, command)
            uow.commit()
        return view

    def submit_form_tx(self, uow: WorkflowUnitOfWork, command: SubmitFormCommand) -> InstanceView:
        """Form gönderimi + koşul + ilk approval task — SAĞLANAN uow, COMMIT ETMEZ."""
        now = self._clock.now()
        tenant = TenantId(command.tenant_id)
        instance = uow.instances.get(command.instance_id)
        instance.guard_not_terminal()
        version = uow.definitions.get_version(instance.definition_version_id.value)
        form_node = version.node(instance.current_node_id)
        if (
            instance.status is not WorkflowInstanceStatus.WAITING
            or form_node["type"] != WorkflowNodeType.FORM.value
        ):
            raise InvalidTransitionError(
                f"form bu durumda gönderilemez: status={instance.status.value}, "
                f"node={form_node['type']}"
            )

        amount = command.form_data.get("amount_minor")
        currency = command.form_data.get("currency")
        if not isinstance(amount, int) or isinstance(amount, bool) or not isinstance(currency, str):
            raise InvalidTransitionError(
                "tutar minor unit (int) + currency (str) çifti olarak zorunludur"
            )

        merged_context: dict[str, Any] = {**instance.context, **command.form_data}
        condition_node = version.node(str(form_node["next"]))
        selection = conditions.evaluate(list(condition_node["config"]["branches"]), merged_context)
        approval_node = version.node(selection.next_node_id)
        chain = [str(role) for role in approval_node["config"]["approver_chain"]]

        # Optimistic guard ÖNCE: eşzamanlı iki submit'i version CAS serialize eder.
        advanced = instance.advance_waiting(
            node_id=str(approval_node["id"]), context=merged_context, now=now
        )
        uow.instances.update_checked(advanced, expected_version=command.expected_version, now=now)

        active_task: WorkflowTask | None = None
        for index, role in enumerate(chain):
            assignee_raw = command.role_assignees.get(role)
            assignee = UserId(UUID(assignee_raw)) if assignee_raw else None
            task = WorkflowTask(
                id=WorkflowTaskId(self._ids.new_uuid()),
                tenant_id=tenant,
                instance_id=instance.id,
                node_id=str(approval_node["id"]),
                step_index=index,
                approver_role=role,
                status=WorkflowTaskStatus.ACTIVE if index == 0 else WorkflowTaskStatus.PENDING,
                version=1,
                assigned_user_id=assignee,
            )
            uow.tasks.add(task, now=now)
            if index == 0:
                active_task = task

        for node, detail in (
            (form_node, {"fields": sorted(command.form_data)}),
            (condition_node, {"branch": selection.branch_id, "explanation": selection.explanation}),
            (approval_node, {"chain": chain, "activated_step_index": 0}),
        ):
            self._append_event(
                uow,
                tenant=tenant,
                instance_id=instance.id,
                event_type=f"node.executed.{node['type']}",
                node_id=str(node["id"]),
                actor_type="user" if node is form_node else "system",
                now=now,
                detail=detail,
            )
        self._enqueue(
            uow,
            tenant=tenant,
            event_type="instance.form_submitted.v1",
            payload={
                "instance_id": str(instance.id.value),
                "tenant_id": str(tenant.value),
                "branch": selection.branch_id,
            },
            now=now,
        )
        return _with_explanation(
            self._view(advanced, active_task=active_task), selection.explanation
        )

    # ------------------------------------------------------------ decide task

    def decide_task(self, command: DecideTaskCommand) -> DecisionResult:
        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)
            result = self.decide_task_tx(
                uow,
                tenant_id=command.tenant_id,
                actor_user_id=command.actor_user_id,
                task_id=command.task_id,
                decision=command.decision,
                idempotency_key=command.idempotency_key,
                approver_role=command.approver_role,
            )
            if result.duplicate:
                uow.rollback()
            else:
                uow.commit()
        return result

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
        """Karar domain işi — SAĞLANAN uow üzerinde, COMMIT ETMEZ.

        Yetki `assigned_user_id` iledir (owner #6): task assignee'si olmayan actor
        UnauthorizedApproverError alır. `approver_role` None ise task'ın kendi rolü
        kullanılır (self-consistent; auth assignee'ye bırakılır).
        """
        now = self._clock.now()
        tenant = TenantId(tenant_id)
        decision_status = _DECISION_TO_STATUS.get(decision)
        if decision_status is None:
            raise InvalidTransitionError(f"geçersiz karar: {decision!r}")

        task = uow.tasks.get(task_id)
        instance = uow.instances.get(task.instance_id.value)

        # Terminal TASK için GERÇEK idempotent replay'i (aynı actor + aynı key) instance
        # terminal guard'ından ÖNCE ele al: nihai adımın (instance'ı tamamlayan) kararı
        # replay edildiğinde TerminalInstanceError değil, güvenli idempotent duplicate
        # dönmeli. Replay DEĞİLSE (geç/farklı karar) SPK-09 semantiği korunur:
        # instance terminal → TerminalInstanceError; instance canlı → DuplicateDecisionError.
        if task.status.is_terminal:
            is_replay = (
                task.decided_by == UserId(actor_user_id)
                and task.idempotency_key == idempotency_key
                and task.decision is not None
            )
            if is_replay:
                return DecisionResult(
                    task_id=task.id.value,
                    step_index=task.step_index,
                    instance_id=instance.id.value,
                    decision=str(task.decision.value) if task.decision else decision,
                    duplicate=True,
                    instance_status=instance.status.value,
                    activated_task_id=None,
                    required_role=task.approver_role,
                )
            instance.guard_not_terminal()  # terminal instance → TerminalInstanceError (SPK-09)
            raise DuplicateDecisionError(
                f"adım {task.step_index} için zaten terminal karar var (tek geçerli karar)"
            )

        instance.guard_not_terminal()

        decided = task.decide(
            actor=UserId(actor_user_id),
            approver_role=approver_role if approver_role is not None else task.approver_role,
            decision=decision_status,
            idempotency_key=idempotency_key,
        )
        if decided is task:  # idempotent replay (aktif task, aynı actor+key)
            return DecisionResult(
                task_id=task.id.value,
                step_index=task.step_index,
                instance_id=instance.id.value,
                decision=str(task.decision.value) if task.decision else decision,
                duplicate=True,
                instance_status=instance.status.value,
                activated_task_id=None,
                required_role=task.approver_role,
            )

        uow.tasks.update_checked(decided, expected_version=task.version, now=now)

        activated_task_id: UUID | None = None
        next_role: str | None = None
        next_assignee: UUID | None = None
        instance_status = instance.status
        if decision_status is WorkflowTaskStatus.APPROVED:
            next_task = uow.tasks.find_by_step(instance.id.value, task.step_index + 1)
            if next_task is not None:
                activated = next_task.activate()
                uow.tasks.update_checked(activated, expected_version=next_task.version, now=now)
                activated_task_id = activated.id.value
                next_role = activated.approver_role
                next_assignee = (
                    activated.assigned_user_id.value if activated.assigned_user_id else None
                )
            else:
                instance = self._finish_instance(uow, instance, tenant=tenant, now=now)
                instance_status = instance.status
        else:
            uow.tasks.cancel_open_for_instance(instance.id.value, now=now)
            uow.timers.cancel_open_for_instance(instance.id.value)
            instance = self._terminate_instance(
                uow, instance, WorkflowInstanceStatus.REJECTED, tenant=tenant, now=now
            )
            self._notify_requester(uow, instance, tenant=tenant, now=now)
            instance_status = instance.status

        self._append_event(
            uow,
            tenant=tenant,
            instance_id=instance.id,
            event_type="task.decided",
            node_id=task.node_id,
            actor_type="user",
            now=now,
            detail={
                "task_id": str(task.id.value),
                "step_index": task.step_index,
                "decision": decision,
                "role": task.approver_role,
            },
        )
        self._enqueue(
            uow,
            tenant=tenant,
            event_type="task.decided.v1",
            payload={
                "instance_id": str(instance.id.value),
                "tenant_id": str(tenant.value),
                "task_id": str(task.id.value),
                "step_index": task.step_index,
                "decision": decision,
            },
            now=now,
        )
        return DecisionResult(
            task_id=task.id.value,
            step_index=task.step_index,
            instance_id=instance.id.value,
            decision=decision,
            duplicate=False,
            instance_status=instance_status.value,
            activated_task_id=activated_task_id,
            required_role=task.approver_role,
            next_approval_role=next_role,
            next_task_assigned_user_id=next_assignee,
        )

    # ------------------------------------------------------------ cancel

    def cancel_instance(self, command: CancelInstanceCommand) -> None:
        now = self._clock.now()
        tenant = TenantId(command.tenant_id)
        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)
            instance = uow.instances.get(command.instance_id)
            instance.guard_not_terminal()
            uow.tasks.cancel_open_for_instance(instance.id.value, now=now)
            uow.timers.cancel_open_for_instance(instance.id.value)
            cancelled = instance.cancel(now=now)
            uow.instances.update_checked(
                cancelled, expected_version=command.expected_version, now=now
            )
            self._append_event(
                uow,
                tenant=tenant,
                instance_id=instance.id,
                event_type="instance.cancelled",
                node_id=instance.current_node_id,
                actor_type="user",
                now=now,
                detail={},
            )
            self._enqueue(
                uow,
                tenant=tenant,
                event_type="instance.cancelled.v1",
                payload={"instance_id": str(instance.id.value), "tenant_id": str(tenant.value)},
                now=now,
            )
            uow.commit()

    # ------------------------------------------------------------ timers/queries

    def schedule_timer(self, command: ScheduleTimerCommand) -> UUID:
        now = self._clock.now()
        timer_id = self._ids.new_uuid()
        with self._uow_factory() as uow:
            uow.set_tenant_context(command.tenant_id)
            result = uow.timers.schedule(command, timer_id=timer_id, now=now)
            uow.commit()
        return result

    def load_instance(self, *, tenant_id: UUID, instance_id: UUID) -> InstanceView:
        with self._uow_factory() as uow:
            uow.set_tenant_context(tenant_id)
            instance = uow.instances.get(instance_id)
            active = next(
                (
                    t
                    for t in uow.tasks.list_for_instance(instance_id)
                    if t.status is WorkflowTaskStatus.ACTIVE
                ),
                None,
            )
            return self._view(instance, active_task=active)

    def get_timeline(self, *, tenant_id: UUID, instance_id: UUID) -> list[TimelineEntry]:
        with self._uow_factory() as uow:
            uow.set_tenant_context(tenant_id)
            uow.instances.get(instance_id)  # varlık + RLS guard; yoksa NotFound
            return uow.events.list_for_instance(instance_id)

    # ------------------------------------------------------------ dispatcher

    def run_dispatch_pass(
        self, *, tenant_id: UUID, worker_id: str, now: datetime | None = None, limit: int = 20
    ) -> DispatchStats:
        moment = now or self._clock.now()
        fired = self._fire_due_timers(
            tenant_id=tenant_id, worker_id=worker_id, now=moment, limit=limit
        )
        claimed = self._claim_events(
            tenant_id=tenant_id, worker_id=worker_id, now=moment, limit=limit
        )
        processed = duplicate = retried = failed = 0
        for event in claimed:
            outcome = self._process_one(tenant_id=tenant_id, event=event, now=moment)
            if outcome == "processed":
                processed += 1
            elif outcome == "duplicate":
                duplicate += 1
            elif outcome == "failed":
                failed += 1
            else:
                retried += 1
        return DispatchStats(
            fired_timers=fired,
            processed=processed,
            duplicate=duplicate,
            retried=retried,
            failed=failed,
        )

    def _fire_due_timers(
        self, *, tenant_id: UUID, worker_id: str, now: datetime, limit: int
    ) -> int:
        fired = 0
        with self._uow_factory() as uow:
            uow.set_tenant_context(tenant_id)
            for timer in uow.timers.claim_due(now=now, limit=limit):
                instance = uow.instances.get(timer.instance_id)
                if instance.status.is_terminal:  # terminal → ateşleme yok, diriltme yok
                    continue
                if not uow.timers.mark_fired(timer.timer_id, worker_id=worker_id, now=now):
                    continue  # yarışı kaybetti — ikinci ateşleme yok
                self._enqueue(
                    uow,
                    tenant=TenantId(tenant_id),
                    event_type="notification.requested.v1",
                    payload={
                        "instance_id": str(timer.instance_id),
                        "tenant_id": str(tenant_id),
                        "purpose": timer.purpose,
                    },
                    now=now,
                )
                fired += 1
            uow.commit()
        return fired

    def _claim_events(
        self, *, tenant_id: UUID, worker_id: str, now: datetime, limit: int
    ) -> list[ClaimedOutboxEvent]:
        with self._uow_factory() as uow:
            uow.set_tenant_context(tenant_id)
            claimed = uow.outbox.claim_due(
                worker_id=worker_id, now=now, lease_seconds=30.0, limit=limit
            )
            uow.commit()
        return claimed

    def _process_one(self, *, tenant_id: UUID, event: ClaimedOutboxEvent, now: datetime) -> str:
        try:
            with self._uow_factory() as uow:
                uow.set_tenant_context(tenant_id)
                is_new = uow.inbox.mark_if_new(
                    event.event_id, consumer=_CONSUMER, tenant_id=tenant_id, now=now
                )
                outcome = "duplicate"
                if is_new:
                    self._handle_event(uow, event, now=now)
                    outcome = "processed"
                uow.outbox.mark_processed(event.outbox_id, now=now)
                uow.commit()
            return outcome
        except Exception as exc:  # tek event hatası worker'ı öldürmez
            with self._uow_factory() as uow:
                uow.set_tenant_context(tenant_id)
                result = uow.outbox.mark_retry_or_failed(event, now=now, error=repr(exc))
                uow.commit()
            return "failed" if result == "failed" else "retry"

    def _handle_event(
        self, uow: WorkflowUnitOfWork, event: ClaimedOutboxEvent, *, now: datetime
    ) -> None:
        # Runtime core'da tek yan-etkili handler: notification niyeti → timeline'a
        # 'notification.dispatched' event'i (gerçek in-app notification kanalı
        # notification modülünde gelecek). Inbox idempotency ikinci side effect'i engeller.
        if event.event_type == "notification.requested.v1":
            instance_id = UUID(str(event.payload["instance_id"]))
            self._append_event(
                uow,
                tenant=TenantId(event.tenant_id),
                instance_id=WorkflowInstanceId(instance_id),
                event_type="notification.dispatched",
                node_id=None,
                actor_type="system",
                now=now,
                detail={"source_event_id": str(event.event_id)},
            )

    # ------------------------------------------------------------ helpers

    def _finish_instance(
        self,
        uow: WorkflowUnitOfWork,
        instance: WorkflowInstance,
        *,
        tenant: TenantId,
        now: datetime,
    ) -> WorkflowInstance:
        version = uow.definitions.get_version(instance.definition_version_id.value)
        approval_node = version.node(instance.current_node_id)
        notify_node = version.node(str(approval_node["next"]))
        end_node = version.node(str(notify_node["next"]))
        uow.timers.cancel_open_for_instance(instance.id.value)
        for node in (notify_node, end_node):
            self._append_event(
                uow,
                tenant=tenant,
                instance_id=instance.id,
                event_type=f"node.executed.{node['type']}",
                node_id=str(node["id"]),
                actor_type="system",
                now=now,
                detail={},
            )
        self._notify_requester(uow, instance, tenant=tenant, now=now, notify_node=notify_node)
        completed = instance.complete(node_id=str(end_node["id"]), now=now)
        uow.instances.update_checked(completed, expected_version=instance.version, now=now)
        return completed

    def _terminate_instance(
        self,
        uow: WorkflowUnitOfWork,
        instance: WorkflowInstance,
        status: WorkflowInstanceStatus,
        *,
        tenant: TenantId,
        now: datetime,
    ) -> WorkflowInstance:
        if status is WorkflowInstanceStatus.REJECTED:
            terminated = instance.reject(now=now)
        else:
            terminated = instance.cancel(now=now)
        uow.instances.update_checked(terminated, expected_version=instance.version, now=now)
        return terminated

    def _notify_requester(
        self,
        uow: WorkflowUnitOfWork,
        instance: WorkflowInstance,
        *,
        tenant: TenantId,
        now: datetime,
        notify_node: dict[str, Any] | None = None,
    ) -> None:
        if notify_node is None:
            version = uow.definitions.get_version(instance.definition_version_id.value)
            notify_node = next(
                n
                for n in version.definition["nodes"]
                if n["type"] == WorkflowNodeType.NOTIFICATION.value
            )
        self._enqueue(
            uow,
            tenant=tenant,
            event_type="notification.requested.v1",
            payload={
                "instance_id": str(instance.id.value),
                "tenant_id": str(tenant.value),
                "recipient_role": str(notify_node["config"]["recipient_role"]),
                "message_key": str(notify_node["config"]["message_key"]),
            },
            now=now,
        )

    def _append_event(
        self,
        uow: WorkflowUnitOfWork,
        *,
        tenant: TenantId,
        instance_id: WorkflowInstanceId,
        event_type: str,
        node_id: str | None,
        actor_type: str,
        now: datetime,
        detail: dict[str, Any],
    ) -> None:
        uow.events.append(
            WorkflowEvent(
                id=WorkflowEventId(self._ids.new_uuid()),
                tenant_id=tenant,
                instance_id=instance_id,
                event_type=event_type,
                occurred_at=now,
                node_id=node_id,
                actor_type=actor_type,
                detail=detail,
            )
        )

    def _enqueue(
        self,
        uow: WorkflowUnitOfWork,
        *,
        tenant: TenantId,
        event_type: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        uow.outbox.enqueue(
            IntegrationEvent(
                id=WorkflowEventId(self._ids.new_uuid()),
                tenant_id=tenant,
                event_type=event_type,
                payload=payload,
                available_at=now,
            ),
            created_at=now,
        )

    def _view(
        self, instance: WorkflowInstance, *, active_task: WorkflowTask | None
    ) -> InstanceView:
        task_view = (
            TaskView(
                task_id=active_task.id.value,
                node_id=active_task.node_id,
                step_index=active_task.step_index,
                approver_role=active_task.approver_role,
                status=active_task.status.value,
                assigned_user_id=(
                    active_task.assigned_user_id.value if active_task.assigned_user_id else None
                ),
            )
            if active_task is not None
            else None
        )
        return InstanceView(
            instance_id=instance.id.value,
            definition_version_id=instance.definition_version_id.value,
            definition_hash=instance.definition_hash,
            status=instance.status.value,
            current_node_id=instance.current_node_id,
            version=instance.version,
            active_task=task_view,
        )


_CONSUMER = "workflow-runtime-worker"


def _version_result(version: WorkflowDefinitionVersion) -> PublishDefinitionResult:
    return PublishDefinitionResult(
        definition_id=version.definition_id.value,
        definition_version_id=version.id.value,
        version_no=version.version_no,
        content_hash=version.content_hash,
    )


def _with_explanation(view: InstanceView, explanation: str) -> InstanceView:
    return InstanceView(
        instance_id=view.instance_id,
        definition_version_id=view.definition_version_id,
        definition_hash=view.definition_hash,
        status=view.status,
        current_node_id=view.current_node_id,
        version=view.version,
        branch_explanation=explanation,
        active_task=view.active_task,
    )
