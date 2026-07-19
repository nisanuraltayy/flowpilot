"""Purchase Request'in onay akışına açtığı application yazma sözleşmesi.

Approval modülü, bir workflow kararının Purchase Request durumuna yansımasını BU
application fonksiyonları üzerinden uygular — `purchase_request.domain`'i DOĞRUDAN
import ETMEZ (dependency-rules §2: cross-context domain importu YASAK; cross-module
yazma command/application API üzerinden). Transition kuralı (IN_APPROVAL→APPROVED/
REJECTED) BURADA, PR domain'inde kalır. Aynı compose transaction'ın parçasıdır;
COMMIT ETMEZ.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from flowpilot.modules.purchase_request.application.ports import PurchaseRequestRepository


@dataclass(frozen=True)
class PurchaseRequestOutcome:
    """Karar sonrası PR özeti (approval sonuç/audit için)."""

    purchase_request_id: UUID | None
    status: str


def resolve_purchase_request_id(
    repo: PurchaseRequestRepository, *, workflow_instance_id: UUID
) -> UUID | None:
    """Workflow instance'a bağlı talebin id'sini döndürür (transition YAPMAZ)."""
    pr = repo.get_by_workflow_instance(workflow_instance_id)
    return pr.id.value if pr is not None else None


def apply_workflow_outcome(
    repo: PurchaseRequestRepository,
    *,
    workflow_instance_id: UUID,
    workflow_status: str,
    now: datetime,
) -> PurchaseRequestOutcome:
    """Workflow terminal durumunu PR'a yansıtır (optimistic CAS ile).

    - `completed` → PR approve, `rejected` → PR reject.
    - Ara durum (henüz sonraki approval adımı) → PR durumu değişmez (in_approval).
    - Talep bulunamazsa `unknown` (kısmi state bırakmaz; çağıran karar verir).
    """
    pr = repo.get_by_workflow_instance(workflow_instance_id)
    if pr is None:
        return PurchaseRequestOutcome(purchase_request_id=None, status="unknown")
    if workflow_status == "completed":
        updated = pr.approve(now=now)
        repo.update_checked(updated, expected_version=pr.version)
        return PurchaseRequestOutcome(purchase_request_id=pr.id.value, status=updated.status.value)
    if workflow_status == "rejected":
        updated = pr.reject(now=now)
        repo.update_checked(updated, expected_version=pr.version)
        return PurchaseRequestOutcome(purchase_request_id=pr.id.value, status=updated.status.value)
    return PurchaseRequestOutcome(purchase_request_id=pr.id.value, status=pr.status.value)
