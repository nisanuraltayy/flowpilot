"""Organizasyon üye yönetimi endpoint'leri (FP-E03-002).

Kurallar:
- İş mantığı YOK: application use-case'leri çağrılır. Response commit'ten SONRA üretilir.
- Actor YALNIZ doğrulanmış `CurrentActor`'dan; organization_id path'ten, membership +
  merkezi authorization ile doğrulanır. Yetki merkezi boundary'de (dağınık rol kontrolü YOK).
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
    get_current_actor,
    get_list_members_handler,
    get_update_member_handler,
)
from flowpilot.modules.authorization.application.access import PermissionDeniedError
from flowpilot.modules.organization.application.member_dto import UpdateMemberCommand
from flowpilot.modules.organization.application.member_errors import (
    ApprovalResponsibilityConflictError,
    FinalOwnerError,
    InvalidMembershipTransitionError,
    InvalidMemberUpdateError,
    MemberActorNotMemberError,
    MemberManagementForbiddenError,
    MemberNotFoundError,
    MemberSelfMutationError,
    MembershipConcurrencyError,
    MembershipRemovedError,
)
from flowpilot.modules.organization.application.member_handlers import (
    ListOrganizationMembersHandler,
    UpdateOrganizationMemberHandler,
)

router = APIRouter(
    prefix="/v1/organizations/{organization_id}/members",
    tags=["members"],
)

_NOT_FOUND = "Kaynak bulunamadi."  # membership yok / cross-tenant / hedef yok — sızdırmaz
_FORBIDDEN = "Bu islem icin yetkiniz yok."
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 100


class MemberItemResponse(BaseModel):
    membership_id: UUID
    user_id: UUID
    email: str | None
    role: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class MembersResponse(BaseModel):
    items: list[MemberItemResponse]


class UpdateMemberBody(BaseModel):
    """Üye güncelleme isteği. role/status'tan en az biri; expected_version zorunlu."""

    role: str | None = Field(default=None, description="Yeni rol: owner/admin/member.")
    status: str | None = Field(default=None, description="Yeni durum: active/suspended/removed.")
    expected_version: int = Field(description="Optimistic concurrency için beklenen sürüm.")


class UpdateMemberResponse(BaseModel):
    membership_id: UUID
    user_id: UUID
    role: str
    status: str
    version: int
    duplicate: bool


@router.get(
    "",
    response_model=MembersResponse,
    summary="Organizasyon üyelerini listele",
    description=(
        "Aktif owner/admin, tenant üyelerini (email dâhil) listeler. Removed üyeler "
        "durumlarıyla listede kalır. provider_subject/auth bilgisi DÖNMEZ. Server-side max "
        "page size ile sınırlı."
    ),
)
def list_members(
    organization_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[ListOrganizationMembersHandler, Depends(get_list_members_handler)],
    limit: int = _DEFAULT_PAGE_SIZE,
) -> MembersResponse:
    bounded = max(1, min(limit, _MAX_PAGE_SIZE))
    try:
        items = handler.handle(
            tenant_id=organization_id, actor_user_id=actor.user_id, limit=bounded
        )
    except MemberActorNotMemberError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from exc

    return MembersResponse(
        items=[
            MemberItemResponse(
                membership_id=item.membership_id,
                user_id=item.user_id,
                email=item.email,
                role=item.role,
                status=item.status,
                version=item.version,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ]
    )


@router.patch(
    "/{user_id}",
    response_model=UpdateMemberResponse,
    summary="Üye rol/durum güncelle",
    description=(
        "Aktif owner/admin bir üyenin rolünü ve/veya durumunu günceller (optimistic "
        "concurrency). Self-mutation, son-owner ihlali, removed hedef, geçersiz geçiş, aktif "
        "onay sorumluluğu → 409; yetkisiz hedef → 403. No-op → duplicate=true."
    ),
)
def update_member(
    organization_id: UUID,
    user_id: UUID,
    body: UpdateMemberBody,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[UpdateOrganizationMemberHandler, Depends(get_update_member_handler)],
) -> UpdateMemberResponse:
    try:
        result = handler.handle(
            UpdateMemberCommand(
                tenant_id=organization_id,
                actor_user_id=actor.user_id,
                target_user_id=user_id,
                new_role=body.role,
                new_status=body.status,
                expected_version=body.expected_version,
            )
        )
    except InvalidMemberUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except MemberActorNotMemberError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except (PermissionDeniedError, MemberManagementForbiddenError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from exc
    except MemberNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except (
        MemberSelfMutationError,
        FinalOwnerError,
        ApprovalResponsibilityConflictError,
        MembershipConcurrencyError,
        MembershipRemovedError,
        InvalidMembershipTransitionError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return UpdateMemberResponse(
        membership_id=result.membership_id,
        user_id=result.user_id,
        role=result.role,
        status=result.status,
        version=result.version,
        duplicate=result.duplicate,
    )
