"""Organizasyon davet endpoint'leri (FP-E03-001, Dilim A).

Kurallar:
- İş mantığı YOK: application use-case'leri çağrılır; transaction/yetki/domain kuralı
  application+domain'dedir. Response commit'ten SONRA üretilir.
- Actor YALNIZ doğrulanmış `CurrentActor`'dan gelir; body'de actor/tenant kabul edilmez.
  organization_id path'ten gelir ve aktif membership + merkezi authorization ile doğrulanır.
- Yetki merkezi authorization boundary'sindedir (dağınık rol kontrolü YOK).
- Ham token + accept_url YALNIZ CREATE cevabında bir kez döner; liste/revoke'ta YOK.
  token_hash HİÇBİR response'a girmez.
- Kabul akışı ve üyelik oluşturma BU dilimde YOK (Dilim B).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from flowpilot.api.deps import (
    CurrentActor,
    get_create_invitation_handler,
    get_current_actor,
    get_list_pending_invitations_handler,
    get_revoke_invitation_handler,
)
from flowpilot.modules.authorization.application.access import PermissionDeniedError
from flowpilot.modules.organization.application.invitation_dto import (
    CreateInvitationCommand,
    RevokeInvitationCommand,
)
from flowpilot.modules.organization.application.invitation_errors import (
    AlreadyActiveMemberError,
    DuplicatePendingInvitationError,
    IdempotencyKeyReuseError,
    InvalidInvitedEmailError,
    InvitationActorNotMemberError,
    InvitationConcurrencyError,
    InvitationNotFoundError,
    InvitationNotRevocableError,
    InvitationRoleNotAllowedError,
)
from flowpilot.modules.organization.application.invitation_handlers import (
    CreateInvitationHandler,
    ListPendingInvitationsHandler,
    RevokeInvitationHandler,
)

router = APIRouter(
    prefix="/v1/organizations/{organization_id}/invitations",
    tags=["invitations"],
)

_NOT_FOUND = "Kaynak bulunamadi."  # membership yok / cross-tenant — varlık sızdırmaz
_FORBIDDEN = "Bu islem icin yetkiniz yok."
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 100  # DoS koruması: server-side max page size (unbounded list YASAK)


class CreateInvitationBody(BaseModel):
    """Davet oluşturma isteği. Bilinmeyen alanlar yok sayılır (mass-assignment yok)."""

    email: str = Field(description="Davet edilecek e-posta (trim + lowercase normalize edilir).")
    role: str = Field(description="Verilecek üyelik rolü: yalnız 'admin' veya 'member'.")


class CreateInvitationResponse(BaseModel):
    """Oluşturma yanıtı — `token` ve `accept_url` YALNIZ burada, bir kez döner."""

    invitation_id: UUID
    invited_email: str
    role: str
    status: str
    expires_at: datetime
    accept_url: str | None
    token: str | None
    duplicate: bool


class PendingInvitationResponse(BaseModel):
    invitation_id: UUID
    invited_email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime


class PendingInvitationsResponse(BaseModel):
    items: list[PendingInvitationResponse]


class RevokeInvitationResponse(BaseModel):
    invitation_id: UUID
    status: str
    duplicate: bool


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateInvitationResponse,
    summary="Organizasyona üye davet et",
    description=(
        "Aktif owner/admin, bir e-postayı admin/member rolüyle davet eder. Güvenli token "
        "üretilir; DB'de YALNIZ SHA-256 hash saklanır. Ham token + accept_url bu cevapta bir "
        "kez döner. Idempotency-Key opsiyoneldir (replay → aynı sonuç, token'sız)."
    ),
)
def create_invitation(
    organization_id: UUID,
    body: CreateInvitationBody,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[CreateInvitationHandler, Depends(get_create_invitation_handler)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> CreateInvitationResponse:
    try:
        result = handler.handle(
            CreateInvitationCommand(
                tenant_id=organization_id,
                actor_user_id=actor.user_id,
                invited_email=body.email,
                role=body.role,
                idempotency_key=(idempotency_key.strip() if idempotency_key else None) or None,
            )
        )
    except (InvalidInvitedEmailError, InvitationRoleNotAllowedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except InvitationActorNotMemberError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from exc
    except (
        AlreadyActiveMemberError,
        DuplicatePendingInvitationError,
        IdempotencyKeyReuseError,
        InvitationConcurrencyError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return CreateInvitationResponse(
        invitation_id=result.invitation_id,
        invited_email=result.invited_email,
        role=result.role,
        status=result.status,
        expires_at=result.expires_at,
        accept_url=result.accept_url,
        token=result.raw_token,
        duplicate=result.duplicate,
    )


@router.get(
    "",
    response_model=PendingInvitationsResponse,
    summary="Bekleyen davetleri listele",
    description=(
        "Aktif owner/admin, tenant'ın bekleyen (pending + süresi dolmamış) davetlerini "
        "listeler. Token/token_hash DÖNMEZ. Server-side max page size ile sınırlı."
    ),
)
def list_invitations(
    organization_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[
        ListPendingInvitationsHandler, Depends(get_list_pending_invitations_handler)
    ],
    limit: int = _DEFAULT_PAGE_SIZE,
) -> PendingInvitationsResponse:
    bounded = max(1, min(limit, _MAX_PAGE_SIZE))
    try:
        items = handler.handle(
            tenant_id=organization_id, actor_user_id=actor.user_id, limit=bounded
        )
    except InvitationActorNotMemberError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from exc

    return PendingInvitationsResponse(
        items=[
            PendingInvitationResponse(
                invitation_id=item.invitation_id,
                invited_email=item.invited_email,
                role=item.role,
                status=item.status,
                expires_at=item.expires_at,
                created_at=item.created_at,
            )
            for item in items
        ]
    )


@router.post(
    "/{invitation_id}/revoke",
    response_model=RevokeInvitationResponse,
    summary="Daveti iptal et (revoke)",
    description=(
        "Aktif owner/admin bekleyen daveti iptal eder. Idempotent: tekrar revoke → aynı "
        "sonuç (duplicate=true). Kabul edilmiş davet → 409; cross-tenant/yok → 404."
    ),
)
def revoke_invitation(
    organization_id: UUID,
    invitation_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[RevokeInvitationHandler, Depends(get_revoke_invitation_handler)],
) -> RevokeInvitationResponse:
    try:
        result = handler.handle(
            RevokeInvitationCommand(
                tenant_id=organization_id,
                actor_user_id=actor.user_id,
                invitation_id=invitation_id,
            )
        )
    except InvitationActorNotMemberError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from exc
    except InvitationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except (InvitationNotRevocableError, InvitationConcurrencyError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return RevokeInvitationResponse(
        invitation_id=result.invitation_id, status=result.status, duplicate=result.duplicate
    )
