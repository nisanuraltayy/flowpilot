"""CreatePurchaseRequest use-case — cross-module ATOMİK orkestrasyon.

Purchase Request kaydı + workflow instance başlangıcı + ilk approval task + event +
outbox AYNI transaction'da commit edilir (compose UnitOfWork). Business logic BURADA;
endpoint/repository/SQLAlchemy modeline gömülmez. Actor membership geçersizse tenant
varlığını sızdırmayan kontrollü hata üretilir.
"""

from __future__ import annotations

from collections.abc import Callable

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
from flowpilot.modules.purchase_request.application.ports import PurchaseRequestUnitOfWork
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
)
from flowpilot.modules.workflow_runtime.application.errors import WorkflowRuntimeError
from flowpilot.modules.workflow_runtime.application.port import (
    WorkflowRuntimeProvisioningPort,
    WorkflowRuntimeTransactionPort,
)
from flowpilot.shared.clock import ClockPort
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
        clock: ClockPort,
        id_generator: IdGeneratorPort,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._memberships = membership_query
        self._provisioning = provisioning
        self._runtime = runtime
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
                ),
            )
            if submitted.active_task is None:
                # İlk approval task oluşmadıysa hiçbir yarım kayıt bırakma (rollback).
                raise FirstApprovalTaskMissingError("ilk approval task oluşmadı")

            linked = request.attach_workflow(workflow_instance_id=started.instance_id, now=now)
            uow.purchase_requests.update_checked(linked, expected_version=request.version)
            uow.commit()

        return CreatePurchaseRequestResult(
            purchase_request_id=request.id.value,
            tenant_id=command.tenant_id,
            workflow_instance_id=started.instance_id,
            status=linked.status.value,
            title=title.value,
            amount_minor=money.amount_minor,
            currency=money.currency,
            current_approval_role=submitted.active_task.approver_role,
            created_at=now,
        )
