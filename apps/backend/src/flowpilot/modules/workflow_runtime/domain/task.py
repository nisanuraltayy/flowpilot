"""WorkflowTask aggregate'i — human task / sequential approval adımı.

Sıralı onay: bir adım approved olmadan sonraki adım aktifleşmez (SPK-04). Bir
task için tek geçerli aktif karar bulunur; tekrar komutları idempotent sonuç
döndürür (SPK-05). Duplicate karar koruması application + optimistic version CAS
ile birlikte DB düzeyinde de zorlanır.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from flowpilot.modules.workflow_runtime.domain.enums import WorkflowTaskStatus
from flowpilot.modules.workflow_runtime.domain.errors import (
    DuplicateDecisionError,
    InvalidTransitionError,
    SequenceOrderError,
    UnauthorizedApproverError,
)
from flowpilot.modules.workflow_runtime.domain.identifiers import (
    WorkflowInstanceId,
    WorkflowTaskId,
)
from flowpilot.shared.identifiers import TenantId, UserId

_DECISION_STATES = frozenset({WorkflowTaskStatus.APPROVED, WorkflowTaskStatus.REJECTED})


@dataclass(frozen=True)
class WorkflowTask:
    """Bir instance içindeki sıralı onay adımı."""

    id: WorkflowTaskId
    tenant_id: TenantId
    instance_id: WorkflowInstanceId
    node_id: str
    step_index: int
    approver_role: str
    status: WorkflowTaskStatus
    version: int
    decided_by: UserId | None = None
    decision: WorkflowTaskStatus | None = None
    idempotency_key: str | None = None

    def activate(self) -> WorkflowTask:
        """pending → active (önceki adım tamamlanınca)."""
        if self.status is not WorkflowTaskStatus.PENDING:
            raise InvalidTransitionError(
                f"task aktive edilemez: {self.status.value} (pending bekleniyor)"
            )
        return replace(self, status=WorkflowTaskStatus.ACTIVE, version=self.version + 1)

    def decide(
        self,
        *,
        actor: UserId,
        approver_role: str,
        decision: WorkflowTaskStatus,
        idempotency_key: str,
    ) -> WorkflowTask:
        """Aktif adıma karar verir. Sıra/yetki/duplicate guard'ları burada.

        Karar zaten verilmişse ve aynı actor + idempotency key ise idempotent
        replay (aynı task döner); farklıysa DuplicateDecisionError.
        """
        if decision not in _DECISION_STATES:
            raise InvalidTransitionError(f"geçersiz karar: {decision!r}")

        if self.status is WorkflowTaskStatus.PENDING:
            raise SequenceOrderError(
                f"adım {self.step_index} henüz aktif değil — önceki adım tamamlanmadan "
                f"karar verilemez"
            )
        if self.status.is_terminal:
            if (
                self.decided_by == actor
                and self.idempotency_key == idempotency_key
                and self.decision is not None
            ):
                return self  # idempotent replay — yeni karar üretmez
            raise DuplicateDecisionError(
                f"adım {self.step_index} için zaten terminal karar var (tek geçerli karar)"
            )
        if self.approver_role != approver_role:
            raise UnauthorizedApproverError(
                f"adım {self.step_index} rolü {self.approver_role!r}; "
                f"{approver_role!r} karar veremez"
            )
        return replace(
            self,
            status=decision,
            decided_by=actor,
            decision=decision,
            idempotency_key=idempotency_key,
            version=self.version + 1,
        )

    def cancel(self) -> WorkflowTask:
        """Açık (pending/active) task'ı iptal eder (instance cancel/reject sonrası)."""
        if self.status.is_terminal:
            return self
        return replace(self, status=WorkflowTaskStatus.CANCELLED, version=self.version + 1)
