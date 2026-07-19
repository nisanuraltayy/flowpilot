"""GetPurchaseRequest use-case — PR detay + workflow durumu/rol özeti.

PR alanları RLS-scoped read query'den; workflow durumu ve current approval role
workflow_runtime port'undan (load_instance) gelir. Timeline ve audit event'leri BU
aşamada döndürülmez. Cross-tenant erişim read query'nin RLS'i ile engellenir.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from flowpilot.modules.purchase_request.application.dto import PurchaseRequestDetail
from flowpilot.modules.purchase_request.application.ports import PurchaseRequestReadQuery
from flowpilot.modules.workflow_runtime.application.errors import WorkflowInstanceNotFoundError
from flowpilot.modules.workflow_runtime.application.port import WorkflowRuntimePort


class GetPurchaseRequestHandler:
    """Tek satın alma talebini (workflow durumu dahil) döndürür."""

    def __init__(
        self, *, read_query: PurchaseRequestReadQuery, runtime: WorkflowRuntimePort
    ) -> None:
        self._query = read_query
        self._runtime = runtime

    def handle(
        self, *, tenant_id: UUID, purchase_request_id: UUID, current_user_id: UUID
    ) -> PurchaseRequestDetail | None:
        detail = self._query.get(
            tenant_id=tenant_id,
            purchase_request_id=purchase_request_id,
            current_user_id=current_user_id,
        )
        if detail is None or detail.workflow_instance_id is None:
            return detail
        try:
            view = self._runtime.load_instance(
                tenant_id=tenant_id, instance_id=detail.workflow_instance_id
            )
        except WorkflowInstanceNotFoundError:
            return detail
        current_role = view.active_task.approver_role if view.active_task else None
        return replace(detail, workflow_status=view.status, current_approval_role=current_role)
