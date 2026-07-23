"""CreatePurchaseRequest use-case — cross-module ATOMİK orkestrasyon.

Purchase Request kaydı + workflow instance başlangıcı + ilk approval task + event +
outbox AYNI transaction'da commit edilir (compose UnitOfWork). Business logic BURADA;
endpoint/repository/SQLAlchemy modeline gömülmez. Actor membership geçersizse tenant
varlığını sızdırmayan kontrollü hata üretilir.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from flowpilot.modules.audit.application.dto import AuditEventType, AuditRecord
from flowpilot.modules.organization.application.contracts import MembershipQuery
from flowpilot.modules.purchase_request.application.dto import (
    CreatePurchaseRequestCommand,
    CreatePurchaseRequestResult,
)
from flowpilot.modules.purchase_request.application.errors import (
    FirstApprovalTaskMissingError,
    MembershipNotActiveError,
    WorkflowConfigurationError,
)
from flowpilot.modules.purchase_request.application.ports import (
    PurchaseRequestUnitOfWork,
    RoleAssigneeResolver,
)
from flowpilot.modules.purchase_request.application.workflow import (
    WORKFLOW_KEY,
    load_default_definition,
)
from flowpilot.modules.purchase_request.domain.identifiers import PurchaseRequestId
from flowpilot.modules.purchase_request.domain.money import Money
from flowpilot.modules.purchase_request.domain.purchase_request import PurchaseRequest
from flowpilot.modules.purchase_request.domain.value_objects import (
    PurchaseRequestDescription,
    PurchaseRequestTitle,
)
from flowpilot.modules.workflow_runtime.application.dto import (
    PublishDefinitionCommand,
    StartInstanceCommand,
    SubmitFormCommand,
    TaskView,
)
from flowpilot.modules.workflow_runtime.application.errors import WorkflowRuntimeError
from flowpilot.modules.workflow_runtime.application.port import (
    WorkflowRuntimeProvisioningPort,
    WorkflowRuntimeTransactionPort,
)
from flowpilot.shared.clock import ClockPort
from flowpilot.shared.errors import DomainError
from flowpilot.shared.identifiers import TenantId, UserId
from flowpilot.shared.ids import IdGeneratorPort

UnitOfWorkFactory = Callable[[], PurchaseRequestUnitOfWork]


class CreatePurchaseRequestHandler:
    """Satın alma talebi oluşturma + workflow başlatma atomik use-case'i."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        membership_query: MembershipQuery,
        provisioning: WorkflowRuntimeProvisioningPort,
        runtime: WorkflowRuntimeTransactionPort,
        role_resolver: RoleAssigneeResolver,
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._memberships = membership_query
        self._provisioning = provisioning
        self._runtime = runtime
        self._role_resolver = role_resolver
        self._clock = clock
        self._ids = id_generator

    def handle(self, command: CreatePurchaseRequestCommand) -> CreatePurchaseRequestResult:
        # 1) Domain girdi doğrulaması (DB'ye dokunmadan; hatalar 422'ye eşlenir).
        money = Money(amount_minor=command.amount_minor, currency=command.currency)
        title = PurchaseRequestTitle(command.title)
        description = PurchaseRequestDescription(command.description)

        # 2) Authorization gate: actor bu tenant'ta AKTİF üye mi? (org contract, RLS).
        membership = self._memberships.find_active(
            tenant_id=command.tenant_id, user_id=command.actor_user_id
        )
        if membership is None:
            raise MembershipNotActiveError("aktif üyelik bulunamadı")

        # 3) Varsayılan workflow'u idempotent provision et (kendi tx'i) → published version.
        try:
            provisioned = self._provisioning.ensure_published_definition(
                PublishDefinitionCommand(
                    tenant_id=command.tenant_id,
                    actor_user_id=command.actor_user_id,
                    definition_key=WORKFLOW_KEY,
                    definition=load_default_definition(),
                    request_id="provision-purchase-request-approval",
                )
            )
        except WorkflowRuntimeError as exc:
            raise WorkflowConfigurationError("varsayılan workflow provision edilemedi") from exc

        # Approval rollerini owner'a idempotent ata + role→assignee eşlemesini çöz
        # (owner #4/#5). Task'lar submit_form'da bu eşlemeyle SABİTLENİR.
        try:
            role_assignees = self._role_resolver.resolve_all(
                tenant_id=command.tenant_id, actor_user_id=command.actor_user_id
            )
        except DomainError as exc:  # aktif owner yok vb. → kontrollü configuration error
            raise WorkflowConfigurationError("onaycı atamaları çözülemedi") from exc

        now = self._clock.now()
        request, _created_event = PurchaseRequest.create(
            id=PurchaseRequestId(self._ids.new_uuid()),
            tenant_id=TenantId(command.tenant_id),
            requested_by=UserId(command.actor_user_id),
            title=title,
            description=description,
            money=money,
            created_at=now,
        )

        # 4) ATOMİK compose transaction: PR + workflow instance + task + event + outbox.
        with self._uow_factory() as uow:
            uow.set_actor_context(command.actor_user_id)
            uow.set_tenant_context(command.tenant_id)

            uow.purchase_requests.add(request)

            started = self._runtime.start_instance_tx(
                uow,
                StartInstanceCommand(
                    tenant_id=command.tenant_id,
                    actor_user_id=command.actor_user_id,
                    definition_version_id=provisioned.definition_version_id,
                    request_id=str(request.id.value),
                    initial_context={"purchase_request_id": str(request.id.value)},
                ),
            )
            submitted = self._runtime.submit_form_tx(
                uow,
                SubmitFormCommand(
                    tenant_id=command.tenant_id,
                    actor_user_id=command.actor_user_id,
                    instance_id=started.instance_id,
                    expected_version=started.version,
                    form_data={
                        "title": title.value,
                        "description": description.value,
                        "amount_minor": money.amount_minor,
                        "currency": money.currency,
                    },
                    request_id=str(request.id.value),
                    role_assignees=role_assignees,
                ),
            )
            # İlk adım self-approval nedeniyle BLOCKED olabilir (talep sahibi = çözülen
            # assignee): görev requester'a atanmaz, active_task None gelir ama blocked_task
            # dolar. Bu geçerli bir sonuçtur (rollback DEĞİL); iş akışı görünür biçimde bloke.
            head_task = submitted.active_task or submitted.blocked_task
            if head_task is None:
                # Hiç approval task oluşmadıysa yarım kayıt bırakma (rollback).
                raise FirstApprovalTaskMissingError("ilk approval task oluşmadı")

            linked = request.attach_workflow(workflow_instance_id=started.instance_id, now=now)
            uow.purchase_requests.update_checked(linked, expected_version=request.version)

            # Denetim timeline'ının başlangıcı: created → started → task_assigned|task_blocked
            # (AYNI transaction; timeline bütünlüğü ve deterministik sıra için).
            self._write_creation_audit(
                uow,
                command,
                pr_id=request.id.value,
                instance_id=started.instance_id,
                task=head_task,
                money=money,
                now=now,
            )
            uow.commit()

        return CreatePurchaseRequestResult(
            purchase_request_id=request.id.value,
            tenant_id=command.tenant_id,
            workflow_instance_id=started.instance_id,
            status=linked.status.value,
            title=title.value,
            amount_minor=money.amount_minor,
            currency=money.currency,
            current_approval_role=head_task.approver_role,
            created_at=now,
        )

    def _write_creation_audit(
        self,
        uow: PurchaseRequestUnitOfWork,
        command: CreatePurchaseRequestCommand,
        *,
        pr_id: UUID,
        instance_id: UUID,
        task: TaskView,
        money: Money,
        now: datetime,
    ) -> None:
        def record(
            event: AuditEventType,
            *,
            role: str | None,
            task_id: UUID | None,
            metadata: dict[str, str | int],
        ) -> AuditRecord:
            return AuditRecord(
                event_id=self._ids.new_uuid(),
                tenant_id=command.tenant_id,
                aggregate_type="purchase_request",
                aggregate_id=pr_id,
                event_type=event,
                occurred_at=now,
                actor_user_id=command.actor_user_id,
                role_key=role,
                task_id=task_id,
                metadata=metadata,
            )

        uow.audit.append(
            record(
                AuditEventType.PURCHASE_REQUEST_CREATED,
                role=None,
                task_id=None,
                metadata={"amount_minor": money.amount_minor, "currency": money.currency},
            )
        )
        uow.audit.append(
            record(
                AuditEventType.WORKFLOW_STARTED,
                role=None,
                task_id=None,
                metadata={"workflow_instance_id": str(instance_id)},
            )
        )
        if task.status == "blocked":
            # Talep sahibi = çözülen assignee → adım blocked (uygun onaycı yok).
            uow.audit.append(
                record(
                    AuditEventType.APPROVAL_TASK_BLOCKED,
                    role=task.approver_role,
                    task_id=task.task_id,
                    metadata={
                        "blocked_reason": task.blocked_reason or "",
                        "requester_user_id": str(command.actor_user_id),
                    },
                )
            )
        else:
            uow.audit.append(
                record(
                    AuditEventType.APPROVAL_TASK_ASSIGNED,
                    role=task.approver_role,
                    task_id=task.task_id,
                    metadata={},
                )
            )
