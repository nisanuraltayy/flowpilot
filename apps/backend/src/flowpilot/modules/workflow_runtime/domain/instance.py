"""WorkflowInstance aggregate'i + geçerli/terminal transition kuralları.

Instance TAM OLARAK bir published version'a (id + hash) sabitlenir (SPK-02).
Terminal instance yeni node başlatamaz (SPK-09) — guard burada merkezîdir ve
application/worker/timer yollarının hepsi bu aggregate üzerinden geçer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from flowpilot.modules.workflow_runtime.domain.enums import WorkflowInstanceStatus
from flowpilot.modules.workflow_runtime.domain.errors import (
    InvalidTransitionError,
    TerminalInstanceError,
)
from flowpilot.modules.workflow_runtime.domain.identifiers import (
    WorkflowDefinitionVersionId,
    WorkflowInstanceId,
)
from flowpilot.shared.identifiers import TenantId

# Geçerli instance geçişleri (domain-boundaries.md §5).
_ALLOWED_TRANSITIONS: dict[WorkflowInstanceStatus, frozenset[WorkflowInstanceStatus]] = {
    WorkflowInstanceStatus.RUNNING: frozenset(
        {
            WorkflowInstanceStatus.WAITING,
            WorkflowInstanceStatus.COMPLETED,
            WorkflowInstanceStatus.REJECTED,
            WorkflowInstanceStatus.CANCELLED,
            WorkflowInstanceStatus.FAILED,
        }
    ),
    WorkflowInstanceStatus.WAITING: frozenset(
        {
            WorkflowInstanceStatus.RUNNING,
            WorkflowInstanceStatus.WAITING,
            WorkflowInstanceStatus.COMPLETED,
            WorkflowInstanceStatus.REJECTED,
            WorkflowInstanceStatus.CANCELLED,
            WorkflowInstanceStatus.FAILED,
        }
    ),
}


@dataclass(frozen=True)
class WorkflowInstance:
    """Bir workflow version'ının tek çalışması."""

    id: WorkflowInstanceId
    tenant_id: TenantId
    definition_version_id: WorkflowDefinitionVersionId
    definition_hash: str
    status: WorkflowInstanceStatus
    current_node_id: str
    context: dict[str, Any]
    version: int

    def guard_not_terminal(self) -> None:
        """Terminal instance hiçbir yoldan ilerletilemez (SPK-09)."""
        if self.status.is_terminal:
            raise TerminalInstanceError(f"terminal instance ({self.status.value}) ilerletilemez")

    def _transition_to(
        self,
        status: WorkflowInstanceStatus,
        *,
        node_id: str,
        context: dict[str, Any] | None,
        now: datetime,
    ) -> WorkflowInstance:
        self.guard_not_terminal()
        allowed = _ALLOWED_TRANSITIONS.get(self.status, frozenset())
        if status not in allowed:
            raise InvalidTransitionError(
                f"geçersiz instance geçişi: {self.status.value} → {status.value}"
            )
        _ = now  # zaman application katmanında persist edilir (updated_at)
        return replace(
            self,
            status=status,
            current_node_id=node_id,
            context=context if context is not None else self.context,
            version=self.version + 1,
        )

    def advance_waiting(
        self, *, node_id: str, context: dict[str, Any], now: datetime
    ) -> WorkflowInstance:
        """Form/koşul sonrası bir sonraki bekleme node'una (approval) ilerler."""
        return self._transition_to(
            WorkflowInstanceStatus.WAITING, node_id=node_id, context=context, now=now
        )

    def complete(self, *, node_id: str, now: datetime) -> WorkflowInstance:
        return self._transition_to(
            WorkflowInstanceStatus.COMPLETED, node_id=node_id, context=None, now=now
        )

    def reject(self, *, now: datetime) -> WorkflowInstance:
        return self._transition_to(
            WorkflowInstanceStatus.REJECTED, node_id=self.current_node_id, context=None, now=now
        )

    def cancel(self, *, now: datetime) -> WorkflowInstance:
        return self._transition_to(
            WorkflowInstanceStatus.CANCELLED, node_id=self.current_node_id, context=None, now=now
        )
