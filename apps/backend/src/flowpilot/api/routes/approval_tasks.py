"""Blocked approval task endpoint'leri (FP-E06-009).

Self-approval nedeniyle blocked kalan approval adımlarını listeler ve — rol ataması
düzeltildikten sonra — güvenli biçimde uygun kullanıcıya çözer. GENEL task reassignment
DEĞİLDİR: yalnız self-approval kaynaklı blocked adım için çalışır.

Kurallar:
- İş mantığı YOK: application use-case'leri çağrılır. Response commit'ten SONRA üretilir.
- Actor YALNIZ doğrulanmış `CurrentActor`'dan; yetki merkezi authorization boundary'de.
- Response'ta provider_subject / auth_provider / JWT gibi hassas identity bilgisi YOK.
- Frontend BU dilime dahil değildir.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from flowpilot.api.deps import (
    CurrentActor,
    get_current_actor,
    get_list_blocked_approval_tasks_handler,
    get_resolve_blocked_approval_task_handler,
)
from flowpilot.modules.approval.application.blocked_task_dto import ResolveBlockedTaskCommand
from flowpilot.modules.approval.application.blocked_task_errors import (
    BlockedTaskActorNotMemberError,
    BlockedTaskNotFoundError,
    BlockedTaskResolveConflictError,
)
from flowpilot.modules.approval.application.blocked_task_handlers import (
    ListBlockedApprovalTasksHandler,
    ResolveBlockedApprovalTaskHandler,
)
from flowpilot.modules.authorization.application.access import PermissionDeniedError

router = APIRouter(
    prefix="/v1/organizations/{organization_id}/approval-tasks",
    tags=["approval-tasks"],
)

_NOT_FOUND = "Kaynak bulunamadi."  # üye değil / cross-tenant / task yok — sızdırmaz
_FORBIDDEN = "Bu islem icin yetkiniz yok."
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 100


class BlockedTaskItemResponse(BaseModel):
    task_id: UUID
    purchase_request_id: UUID | None
    approver_role: str
    status: str
    blocked_reason: str | None
    requester_user_id: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime


class BlockedTasksResponse(BaseModel):
    items: list[BlockedTaskItemResponse]


class ResolveBlockedTaskResponse(BaseModel):
    task_id: UUID
    purchase_request_id: UUID | None
    approver_role: str
    status: str
    assigned_user_id: UUID
    version: int


@router.get(
    "/blocked",
    response_model=BlockedTasksResponse,
    summary="Blocked approval task'ları listele",
    description=(
        "Aktif owner/admin, self-approval nedeniyle blocked kalan approval adımlarını listeler. "
        "Deterministik sıra + server-side max page size. Hassas identity DÖNMEZ."
    ),
)
def list_blocked_tasks(
    organization_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[
        ListBlockedApprovalTasksHandler, Depends(get_list_blocked_approval_tasks_handler)
    ],
    limit: int = _DEFAULT_PAGE_SIZE,
) -> BlockedTasksResponse:
    bounded = max(1, min(limit, _MAX_PAGE_SIZE))
    try:
        items = handler.handle(
            tenant_id=organization_id, actor_user_id=actor.user_id, limit=bounded
        )
    except BlockedTaskActorNotMemberError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from exc

    return BlockedTasksResponse(
        items=[
            BlockedTaskItemResponse(
                task_id=item.task_id,
                purchase_request_id=item.purchase_request_id,
                approver_role=item.approver_role,
                status=item.status,
                blocked_reason=item.blocked_reason,
                requester_user_id=item.requester_user_id,
                version=item.version,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ]
    )


@router.post(
    "/{task_id}/resolve-assignment",
    response_model=ResolveBlockedTaskResponse,
    summary="Blocked approval adımını uygun kullanıcıya çöz",
    description=(
        "Aktif owner/admin, self-approval nedeniyle blocked kalan adımı mevcut aktif role "
        "assignment'taki uygun kullanıcıya atar (keyfi user_id ALINMAZ). Task blocked değil / "
        "uygun atama yok / aday requester veya aktif değil / eşzamanlı çakışma → 409."
    ),
)
def resolve_blocked_task(
    organization_id: UUID,
    task_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[
        ResolveBlockedApprovalTaskHandler, Depends(get_resolve_blocked_approval_task_handler)
    ],
) -> ResolveBlockedTaskResponse:
    try:
        result = handler.handle(
            ResolveBlockedTaskCommand(
                tenant_id=organization_id,
                actor_user_id=actor.user_id,
                task_id=task_id,
            )
        )
    except BlockedTaskActorNotMemberError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from exc
    except BlockedTaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except BlockedTaskResolveConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return ResolveBlockedTaskResponse(
        task_id=result.task_id,
        purchase_request_id=result.purchase_request_id,
        approver_role=result.approver_role,
        status=result.status,
        assigned_user_id=result.assigned_user_id,
        version=result.version,
    )
