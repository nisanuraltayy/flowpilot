"""Workflow approval rol atama endpoint'leri (FP-E10-004).

owner/admin, approval role_key'lerini (team_manager/finance/general_manager) gerçek AKTİF
üyelere atar. Bu, org-yönetişim rolünden (owner/admin/member) AYRIDIR.

Kurallar:
- İş mantığı YOK: application use-case'leri çağrılır. Response commit'ten SONRA üretilir.
- Actor YALNIZ doğrulanmış `CurrentActor`'dan; organization_id path'ten, membership +
  merkezi authorization ile doğrulanır (dağınık rol kontrolü YOK).
- Response'ta provider_subject / auth_provider / JWT gibi hassas identity bilgisi YOK.
- Frontend BU dilime dahil değildir.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from flowpilot.api.deps import (
    CurrentActor,
    get_assign_approval_role_handler,
    get_current_actor,
    get_list_approval_roles_handler,
)
from flowpilot.modules.approval.application.role_assignment_dto import AssignApprovalRoleCommand
from flowpilot.modules.approval.application.role_assignment_errors import (
    ApprovalRoleActorNotMemberError,
    ApprovalRoleAssignmentConcurrencyError,
    ApprovalRoleExpectedVersionRequiredError,
    ApprovalRoleTargetNotActiveError,
    ApprovalRoleTargetNotFoundError,
    InvalidApprovalRoleKeyError,
)
from flowpilot.modules.approval.application.role_assignment_handlers import (
    AssignApprovalRoleHandler,
    ListApprovalRoleAssignmentsHandler,
)
from flowpilot.modules.authorization.application.access import PermissionDeniedError

router = APIRouter(
    prefix="/v1/organizations/{organization_id}/approval-roles",
    tags=["approval-roles"],
)

_NOT_FOUND = "Kaynak bulunamadi."  # üye değil / cross-tenant / hedef yok — sızdırmaz
_FORBIDDEN = "Bu islem icin yetkiniz yok."


class ApprovalRoleItemResponse(BaseModel):
    assignment_id: UUID
    role_key: str
    assigned_user_id: UUID
    assigned_user_email: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ApprovalRolesResponse(BaseModel):
    items: list[ApprovalRoleItemResponse]


class AssignApprovalRoleBody(BaseModel):
    """Rol atama isteği. Mevcut aktif atama varsa expected_version zorunludur."""

    user_id: UUID = Field(description="Atanacak kullanıcının FlowPilot user_id'si.")
    expected_version: int | None = Field(
        default=None, description="Mevcut aktif atamanın beklenen sürümü (optimistic concurrency)."
    )


class AssignApprovalRoleResponse(BaseModel):
    assignment_id: UUID
    role_key: str
    assigned_user_id: UUID
    assigned_user_email: str | None
    status: str
    version: int
    duplicate: bool


@router.get(
    "",
    response_model=ApprovalRolesResponse,
    summary="Approval rol atamalarını listele",
    description=(
        "Aktif owner/admin, tenant'ın aktif approval rol atamalarını (team_manager → finance "
        "→ general_manager sırasında, email dâhil) listeler. provider_subject/auth DÖNMEZ."
    ),
)
def list_approval_roles(
    organization_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[
        ListApprovalRoleAssignmentsHandler, Depends(get_list_approval_roles_handler)
    ],
) -> ApprovalRolesResponse:
    try:
        items = handler.handle(tenant_id=organization_id, actor_user_id=actor.user_id)
    except ApprovalRoleActorNotMemberError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from exc

    return ApprovalRolesResponse(
        items=[
            ApprovalRoleItemResponse(
                assignment_id=item.assignment_id,
                role_key=item.role_key,
                assigned_user_id=item.assigned_user_id,
                assigned_user_email=item.assigned_user_email,
                status=item.status,
                version=item.version,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ]
    )


@router.put(
    "/{role_key}",
    response_model=AssignApprovalRoleResponse,
    summary="Approval rolünü bir üyeye ata",
    description=(
        "Aktif owner/admin, bir approval role_key'i gerçek bir AKTİF üyeye atar (optimistic "
        "concurrency). Aynı kullanıcı → duplicate=true (yeni atama/audit YOK). Geçersiz role_key "
        "→ 422; yetkisiz → 403; hedef üye değil → 404; hedef aktif değil / stale version / "
        "eşzamanlı çakışma → 409. Mevcut workflow task'ları DEĞİŞTİRMEZ."
    ),
)
def assign_approval_role(
    organization_id: UUID,
    role_key: str,
    body: AssignApprovalRoleBody,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[AssignApprovalRoleHandler, Depends(get_assign_approval_role_handler)],
) -> AssignApprovalRoleResponse:
    try:
        result = handler.handle(
            AssignApprovalRoleCommand(
                tenant_id=organization_id,
                actor_user_id=actor.user_id,
                role_key=role_key,
                target_user_id=body.user_id,
                expected_version=body.expected_version,
            )
        )
    except (InvalidApprovalRoleKeyError, ApprovalRoleExpectedVersionRequiredError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except ApprovalRoleActorNotMemberError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from exc
    except ApprovalRoleTargetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except (
        ApprovalRoleTargetNotActiveError,
        ApprovalRoleAssignmentConcurrencyError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AssignApprovalRoleResponse(
        assignment_id=result.assignment_id,
        role_key=result.role_key,
        assigned_user_id=result.assigned_user_id,
        assigned_user_email=result.assigned_user_email,
        status=result.status,
        version=result.version,
        duplicate=result.duplicate,
    )
