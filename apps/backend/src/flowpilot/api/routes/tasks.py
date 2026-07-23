"""Personal task inbox + approval decision HTTP endpoint'leri.

Kurallar:
- İş mantığı YOK: application use-case'i (`DecideApprovalTaskHandler`) çağrılır;
  transaction/state transition/onay sırası domain+application'dadır. Response YALNIZ
  transaction commit edildikten SONRA üretilir.
- Actor YALNIZ doğrulanmış `CurrentActor`'dan gelir; body'de actor/tenant kabul edilmez.
  organization_id path'ten gelir ama aktif membership ile doğrulanır.
- Karar yetkisi task'a atanmış kullanıcıdadır (owner #6). Self-approval MVP'de SERBEST
  (owner #7, ASM-0016). Yetkisiz/atanmamış → varlık sızdırmayan 404.
- Idempotency-Key ZORUNLU header; aynı key replay → aynı sonuç, farklı payload → 409.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from flowpilot.api.deps import (
    CurrentActor,
    get_current_actor,
    get_decide_approval_task_handler,
    get_membership_query,
    get_task_inbox_query,
)
from flowpilot.modules.approval.application.decide_handler import DecideApprovalTaskHandler
from flowpilot.modules.approval.application.dto import DecideApprovalTaskCommand
from flowpilot.modules.approval.application.errors import (
    ApprovalMembershipNotActiveError,
    ApprovalTaskNotAssignedError,
    DuplicateDecisionConflictError,
    InvalidApprovalCommentError,
    InvalidApprovalDecisionError,
    SelfApprovalConflictError,
)
from flowpilot.modules.organization.application.contracts import MembershipQuery
from flowpilot.modules.purchase_request.application.ports import TaskInboxQuery

router = APIRouter(
    prefix="/v1/organizations/{organization_id}/tasks",
    tags=["tasks"],
)

_NOT_FOUND = "Kaynak bulunamadi."  # membership yok / atanmamış / cross-tenant — sızdırmaz
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 100  # DoS koruması: server-side max page size (unbounded list YASAK)


class DecideTaskBody(BaseModel):
    """Onay kararı isteği. Bilinmeyen alanlar yok sayılır (mass-assignment yok)."""

    decision: str = Field(description="'approve' veya 'reject'.")
    comment: str | None = Field(default=None, description="İsteğe bağlı açıklama (≤2000).")


class DecideTaskResponse(BaseModel):
    task_id: UUID
    decision: str
    purchase_request_id: UUID
    purchase_request_status: str
    workflow_status: str
    next_approval_role: str | None
    decided_at: datetime
    duplicate: bool


class InboxItemResponse(BaseModel):
    task_id: UUID
    purchase_request_id: UUID
    purchase_request_title: str
    amount_minor: int
    currency: str
    required_role: str
    status: str
    workflow_instance_id: UUID
    created_at: datetime
    due_at: datetime | None


class InboxResponse(BaseModel):
    items: list[InboxItemResponse]


def _require_active_membership(
    membership_query: MembershipQuery, *, organization_id: UUID, user_id: UUID
) -> None:
    if membership_query.find_active(tenant_id=organization_id, user_id=user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


@router.get(
    "/inbox",
    response_model=InboxResponse,
    summary="Kişisel onay kutusu",
    description=(
        "Actor'a ATANMIŞ (assigned_user_id) AKTİF onay task'ları, en yeni önce. Başka "
        "kullanıcının task'ı görünmez. Server-side max page size ile sınırlı."
    ),
)
def get_task_inbox(
    organization_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    membership_query: Annotated[MembershipQuery, Depends(get_membership_query)],
    inbox_query: Annotated[TaskInboxQuery, Depends(get_task_inbox_query)],
    limit: int = _DEFAULT_PAGE_SIZE,
) -> InboxResponse:
    _require_active_membership(
        membership_query, organization_id=organization_id, user_id=actor.user_id
    )
    bounded = max(1, min(limit, _MAX_PAGE_SIZE))
    items = inbox_query.list_pending_for_user(
        tenant_id=organization_id, user_id=actor.user_id, limit=bounded
    )
    return InboxResponse(
        items=[
            InboxItemResponse(
                task_id=item.task_id,
                purchase_request_id=item.purchase_request_id,
                purchase_request_title=item.purchase_request_title,
                amount_minor=item.amount_minor,
                currency=item.currency,
                required_role=item.required_role,
                status=item.status,
                workflow_instance_id=item.workflow_instance_id,
                created_at=item.created_at,
                due_at=item.due_at,
            )
            for item in items
        ]
    )


@router.post(
    "/{task_id}/decision",
    response_model=DecideTaskResponse,
    summary="Onay task'ı için karar ver (approve/reject)",
    description=(
        "Atanmış onaycı task'ı onaylar/reddeder; sonraki onay adımı, PR durumu, karar "
        "kaydı, runtime event/outbox ve audit AYNI transaction'da yazılır. Idempotency-Key "
        "ZORUNLU: aynı key replay → aynı sonuç; farklı payload/çakışan karar → 409."
    ),
)
def decide_task(
    organization_id: UUID,
    task_id: UUID,
    body: DecideTaskBody,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[DecideApprovalTaskHandler, Depends(get_decide_approval_task_handler)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> DecideTaskResponse:
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Idempotency-Key header zorunludur.",
        )
    try:
        result = handler.handle(
            DecideApprovalTaskCommand(
                tenant_id=organization_id,
                actor_user_id=actor.user_id,
                task_id=task_id,
                decision=body.decision,
                comment=body.comment,
                idempotency_key=idempotency_key.strip(),
            )
        )
    except (InvalidApprovalDecisionError, InvalidApprovalCommentError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except (ApprovalMembershipNotActiveError, ApprovalTaskNotAssignedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except SelfApprovalConflictError as exc:
        # Talep sahibi kendi talebindeki adımı sonuçlandıramaz (FP-E06-009) — güvenli 409.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DuplicateDecisionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Karar çakışması: bu task için karar zaten verildi.",
        ) from exc

    return DecideTaskResponse(
        task_id=result.task_id,
        decision=result.decision,
        purchase_request_id=result.purchase_request_id,
        purchase_request_status=result.purchase_request_status,
        workflow_status=result.workflow_status,
        next_approval_role=result.next_approval_role,
        decided_at=result.decided_at,
        duplicate=result.duplicate,
    )
