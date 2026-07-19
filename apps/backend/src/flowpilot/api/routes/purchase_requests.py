"""Purchase Request HTTP endpoint'leri (ilk dikey dilim).

Kurallar:
- İş mantığı YOK: application use-case'leri çağrılır; transaction/repository burada
  yeniden yazılmaz. Response commit edildikten SONRA üretilir.
- Actor YALNIZ doğrulanmış `CurrentActor`'dan gelir; body'de actor/tenant/workflow/
  approver kabul edilmez. organization_id path'ten gelir ama membership ile doğrulanır.
- Domain/ORM nesnesi değil, Pydantic response modeli döner.
- Approval decision / task inbox / audit timeline endpoint'leri BU aşamada YOK.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from flowpilot.api.deps import (
    CurrentActor,
    get_create_purchase_request_handler,
    get_current_actor,
    get_get_purchase_request_handler,
    get_membership_query,
)
from flowpilot.modules.organization.application.contracts import MembershipQuery
from flowpilot.modules.purchase_request.application.create_handler import (
    CreatePurchaseRequestHandler,
)
from flowpilot.modules.purchase_request.application.dto import CreatePurchaseRequestCommand
from flowpilot.modules.purchase_request.application.errors import (
    FirstApprovalTaskMissingError,
    InvalidDescriptionError,
    InvalidMoneyError,
    InvalidTitleError,
    MembershipNotActiveError,
    PurchaseRequestConcurrencyError,
    WorkflowConfigurationError,
)
from flowpilot.modules.purchase_request.application.get_handler import GetPurchaseRequestHandler

router = APIRouter(
    prefix="/v1/organizations/{organization_id}/purchase-requests",
    tags=["purchase-requests"],
)

_NOT_FOUND = "Kaynak bulunamadi."  # membership yok / cross-tenant — varlık sızdırmaz


class CreatePurchaseRequestBody(BaseModel):
    """Satın alma talebi isteği. Bilinmeyen alanlar yok sayılır (mass-assignment yok)."""

    title: str = Field(description="Talep başlığı (1-200 karakter).")
    description: str | None = Field(default=None, description="İsteğe bağlı gerekçe.")
    amount_minor: int = Field(description="Tutar minor unit (kuruş); > 0.")
    currency: str = Field(description="ISO-4217; MVP'de yalnız TRY.")


class PurchaseRequestCreatedResponse(BaseModel):
    purchase_request_id: UUID
    organization_id: UUID
    workflow_instance_id: UUID
    status: str
    title: str
    amount_minor: int
    currency: str
    current_approval_role: str | None
    created_at: datetime


class PurchaseRequestDetailResponse(BaseModel):
    purchase_request_id: UUID
    organization_id: UUID
    requested_by_current_user: bool
    title: str
    description: str | None
    amount_minor: int
    currency: str
    status: str
    workflow_instance_id: UUID | None
    workflow_status: str | None
    current_approval_role: str | None
    created_at: datetime
    updated_at: datetime


def _require_active_membership(
    membership_query: MembershipQuery, *, organization_id: UUID, user_id: UUID
) -> None:
    if membership_query.find_active(tenant_id=organization_id, user_id=user_id) is None:
        # Üyelik yoksa tenant varlığını SIZDIRMA: 404.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=PurchaseRequestCreatedResponse,
    summary="Satın alma talebi oluştur",
    description=(
        "Aktif üye olunan organizasyonda satın alma talebi oluşturur; varsayılan "
        "onay workflow'unu başlatır ve ilk approval task'ını AYNI transaction'da üretir."
    ),
)
def create_purchase_request(
    organization_id: UUID,
    body: CreatePurchaseRequestBody,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[CreatePurchaseRequestHandler, Depends(get_create_purchase_request_handler)],
) -> PurchaseRequestCreatedResponse:
    try:
        result = handler.handle(
            CreatePurchaseRequestCommand(
                actor_user_id=actor.user_id,
                tenant_id=organization_id,
                title=body.title,
                description=body.description,
                amount_minor=body.amount_minor,
                currency=body.currency,
            )
        )
    except (InvalidMoneyError, InvalidTitleError, InvalidDescriptionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except MembershipNotActiveError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    except WorkflowConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Onay akışı yapılandırması şu anda kullanılamıyor.",
        ) from exc
    except PurchaseRequestConcurrencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Eşzamanlı değişiklik çakışması."
        ) from exc
    except FirstApprovalTaskMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Onay adımı oluşturulamadı; talep kaydedilmedi.",
        ) from exc

    return PurchaseRequestCreatedResponse(
        purchase_request_id=result.purchase_request_id,
        organization_id=result.tenant_id,
        workflow_instance_id=result.workflow_instance_id,
        status=result.status,
        title=result.title,
        amount_minor=result.amount_minor,
        currency=result.currency,
        current_approval_role=result.current_approval_role,
        created_at=result.created_at,
    )


@router.get(
    "/{purchase_request_id}",
    response_model=PurchaseRequestDetailResponse,
    summary="Satın alma talebi detayını getir",
    description="Talep + workflow durumu + current approval role. Timeline/audit YOK.",
)
def get_purchase_request(
    organization_id: UUID,
    purchase_request_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    membership_query: Annotated[MembershipQuery, Depends(get_membership_query)],
    handler: Annotated[GetPurchaseRequestHandler, Depends(get_get_purchase_request_handler)],
) -> PurchaseRequestDetailResponse:
    _require_active_membership(
        membership_query, organization_id=organization_id, user_id=actor.user_id
    )
    detail = handler.handle(
        tenant_id=organization_id,
        purchase_request_id=purchase_request_id,
        current_user_id=actor.user_id,
    )
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return PurchaseRequestDetailResponse(
        purchase_request_id=detail.purchase_request_id,
        organization_id=detail.tenant_id,
        requested_by_current_user=detail.requested_by_current_user,
        title=detail.title,
        description=detail.description,
        amount_minor=detail.amount_minor,
        currency=detail.currency,
        status=detail.status,
        workflow_instance_id=detail.workflow_instance_id,
        workflow_status=detail.workflow_status,
        current_approval_role=detail.current_approval_role,
        created_at=detail.created_at,
        updated_at=detail.updated_at,
    )
