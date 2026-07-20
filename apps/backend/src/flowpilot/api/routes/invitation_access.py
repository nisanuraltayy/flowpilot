"""Davet önizleme + kabul endpoint'leri (FP-E03-001, Dilim B) — TOP-LEVEL /v1/invitations.

Bu endpoint'ler org-scope path'i DEĞİL; org kimliği query/body'den gelir ve RLS tenant
context'ini kurmak için kullanılır. Preview auth'suz (capability = token); accept auth'lu.

Kurallar:
- İş mantığı YOK: application use-case'leri çağrılır; transaction/domain kuralı orada.
- Response'ta token/token_hash/tam e-posta YOK. Hatalar varlık/tenant sızdırmaz.
- Kabul yetkisi = capability token + authenticated actor + e-posta eşleşmesi (owner/admin
  permission'ına TABİ DEĞİL).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from flowpilot.api.deps import (
    CurrentActor,
    get_accept_invitation_handler,
    get_current_actor,
    get_preview_invitation_handler,
)
from flowpilot.modules.organization.application.invitation_accept import (
    AcceptInvitationHandler,
    PreviewInvitationHandler,
)
from flowpilot.modules.organization.application.invitation_dto import AcceptInvitationCommand
from flowpilot.modules.organization.application.invitation_errors import (
    IdempotencyKeyReuseError,
    InvitationAcceptedByOtherError,
    InvitationConcurrencyError,
    InvitationEmailMismatchError,
    InvitationEmailMissingError,
    InvitationExpiredError,
    InvitationNotAcceptableError,
    InvitationNotFoundError,
    MembershipInactiveConflictError,
)

router = APIRouter(prefix="/v1/invitations", tags=["invitations"])

_NOT_FOUND = "Kaynak bulunamadi."  # bilinmeyen/revoked/cross-tenant/başkasına ait — sızdırmaz
_FORBIDDEN = "Davet e-postasi eslesmiyor."
_EXPIRED = "Davet suresi dolmus."
_CONFLICT = "Islem tamamlanamadi (cakisma)."


class PreviewInvitationResponse(BaseModel):
    organization_id: UUID
    organization_name: str
    role: str
    expires_at: datetime
    status: str


class AcceptInvitationBody(BaseModel):
    """Davet kabul isteği. Bilinmeyen alanlar yok sayılır (mass-assignment yok)."""

    organization_id: UUID = Field(description="Davetin ait olduğu organizasyon (tenant) kimliği.")
    token: str = Field(description="Ham davet token'ı (yalnız hash ile karşılaştırılır).")


class AcceptInvitationResponse(BaseModel):
    organization_id: UUID
    membership_id: UUID
    role: str
    status: str
    duplicate: bool


@router.get(
    "/preview",
    response_model=PreviewInvitationResponse,
    summary="Daveti güvenli biçimde önizle (auth gerekmez)",
    description=(
        "Token + org ile davetin minimal bilgisini döndürür. Tam e-posta/token DÖNMEZ. "
        "Bilinmeyen/revoked/yanlış tenant → 404; süresi dolmuş → 410."
    ),
)
def preview_invitation(
    org: UUID,
    token: str,
    handler: Annotated[PreviewInvitationHandler, Depends(get_preview_invitation_handler)],
) -> PreviewInvitationResponse:
    try:
        result = handler.handle(organization_id=org, raw_token=token)
    except InvitationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except InvitationExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=_EXPIRED) from exc

    return PreviewInvitationResponse(
        organization_id=result.organization_id,
        organization_name=result.organization_name,
        role=result.role,
        expires_at=result.expires_at,
        status=result.status,
    )


@router.post(
    "/accept",
    response_model=AcceptInvitationResponse,
    summary="Daveti kabul et (auth zorunlu)",
    description=(
        "Authenticated actor, e-postası davet e-postasıyla eşleşiyorsa daveti kabul eder ve "
        "davet rolüyle AKTİF üye olur (tek transaction). Tek kullanımlık: aynı actor replay → "
        "duplicate=true; başka actor → 404. Zaten aktif üye → rol korunur, duplicate=true."
    ),
)
def accept_invitation(
    body: AcceptInvitationBody,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[AcceptInvitationHandler, Depends(get_accept_invitation_handler)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AcceptInvitationResponse:
    try:
        result = handler.handle(
            AcceptInvitationCommand(
                organization_id=body.organization_id,
                actor_user_id=actor.user_id,
                raw_token=body.token,
                idempotency_key=(idempotency_key.strip() if idempotency_key else None) or None,
            )
        )
    except (InvitationEmailMismatchError, InvitationEmailMissingError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN) from exc
    except (InvitationNotFoundError, InvitationAcceptedByOtherError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except InvitationExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=_EXPIRED) from exc
    except (
        MembershipInactiveConflictError,
        InvitationNotAcceptableError,
        InvitationConcurrencyError,
        IdempotencyKeyReuseError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_CONFLICT) from exc

    return AcceptInvitationResponse(
        organization_id=result.organization_id,
        membership_id=result.membership_id,
        role=result.role,
        status=result.status,
        duplicate=result.duplicate,
    )
