"""WorkflowTask aggregate'i — human task / sequential approval adımı.

Sıralı onay: bir adım approved olmadan sonraki adım aktifleşmez (SPK-04). Bir
task için tek geçerli aktif karar bulunur; tekrar komutları idempotent sonuç
döndürür (SPK-05). Duplicate karar koruması application + optimistic version CAS
ile birlikte DB düzeyinde de zorlanır.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from flowpilot.modules.workflow_runtime.domain.enums import WorkflowTaskStatus
from flowpilot.modules.workflow_runtime.domain.errors import (
    DuplicateDecisionError,
    InvalidTransitionError,
    SequenceOrderError,
    TaskNotBlockedError,
    UnauthorizedApproverError,
)
from flowpilot.modules.workflow_runtime.domain.identifiers import (
    WorkflowInstanceId,
    WorkflowTaskId,
)
from flowpilot.shared.identifiers import TenantId, UserId

_DECISION_STATES = frozenset({WorkflowTaskStatus.APPROVED, WorkflowTaskStatus.REJECTED})

# Uygun onaycı yok (çözülen assignee talep sahibi) → adım blocked. Tek geçerli değer.
SELF_APPROVAL_BLOCKED_REASON = "self_approval_no_eligible_assignee"


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
    # Task oluşturulduğu anda role'e atanmış kullanıcı SABİTLENİR (owner kararı #5);
    # rol ataması sonradan değişse bile bu task'ın assignee'si DEĞİŞMEZ. None ise
    # (assignee-öncesi runtime testleri) yetki role üzerinden değerlendirilir.
    assigned_user_id: UserId | None = None
    # Self-approval engeli (FP-E06-009): oluşturma anında çözülen assignee talep sahibiyse
    # görev requester'a ATANMAZ (assigned_user_id None) ve `blocked_reason` ön-işaretlenir.
    # PENDING bir adımda ön-işaretli reason, adım aktive olurken BLOCKED'a materyalize olur.
    blocked_reason: str | None = None
    blocked_at: datetime | None = None

    @property
    def is_self_conflict(self) -> bool:
        """Oluşturma anındaki assignee talep sahibiydi (uygun onaycı yok)."""
        return self.blocked_reason == SELF_APPROVAL_BLOCKED_REASON

    def activate(self, *, now: datetime) -> WorkflowTask:
        """pending → active (önceki adım tamamlanınca).

        Ön-işaretli self-conflict adımı ACTIVE yerine BLOCKED'a geçer (talep sahibine
        atanmaz, inbox'ta görünmez). Workflow bu adımda durur; yalnız resolve ile açılır.
        """
        if self.status is not WorkflowTaskStatus.PENDING:
            raise InvalidTransitionError(
                f"task aktive edilemez: {self.status.value} (pending bekleniyor)"
            )
        if self.is_self_conflict:
            return replace(
                self,
                status=WorkflowTaskStatus.BLOCKED,
                blocked_at=now,
                version=self.version + 1,
            )
        return replace(self, status=WorkflowTaskStatus.ACTIVE, version=self.version + 1)

    def resolve_assignment(self, *, new_assignee: UserId, now: datetime) -> WorkflowTask:
        """blocked → active: yalnız self-approval nedeniyle blocked adımı uygun kullanıcıya
        atar (blocked_reason temizlenir). Yeni kullanıcının talep sahibi olmadığı ve aktif
        üye olduğu ÇAĞIRAN tarafında (runtime/handler) doğrulanır."""
        if self.status is not WorkflowTaskStatus.BLOCKED or not self.is_self_conflict:
            raise TaskNotBlockedError(
                f"adım {self.step_index} self-approval nedeniyle blocked değil — resolve edilemez"
            )
        return replace(
            self,
            status=WorkflowTaskStatus.ACTIVE,
            assigned_user_id=new_assignee,
            blocked_reason=None,
            blocked_at=None,
            version=self.version + 1,
        )

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

        if self.status is WorkflowTaskStatus.BLOCKED:
            raise SequenceOrderError(
                f"adım {self.step_index} blocked (uygun onaycı yok) — karar verilemez, "
                f"önce assignment resolve edilmelidir"
            )
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
        # Yetki: assignee sabitlenmişse YALNIZ o kullanıcı karar verebilir (owner #6).
        # Assignee yoksa (legacy/test) rol eşleşmesine düşülür.
        if self.assigned_user_id is not None:
            if actor != self.assigned_user_id:
                raise UnauthorizedApproverError(
                    f"adım {self.step_index} yalnız atanmış kullanıcısı tarafından "
                    f"karar verilebilir"
                )
        elif self.approver_role != approver_role:
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
