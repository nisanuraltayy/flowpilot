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
    get_audit_timeline_query,
    get_create_purchase_request_handler,
    get_current_actor,
    get_get_purchase_request_handler,
    get_membership_query,
    get_purchase_request_read_query,
)
from flowpilot.modules.audit.application.ports import AuditTimelineQueryPort
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
from flowpilot.modules.purchase_request.application.ports import PurchaseRequestReadQuery

router = APIRouter(
    prefix="/v1/organizations/{organization_id}/purchase-requests",
    tags=["purchase-requests"],
)

_NOT_FOUND = "Kaynak bulunamadi."  # membership yok / cross-tenant — varlık sızdırmaz
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 100  # DoS koruması: server-side max page size (unbounded list YASAK)


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


class PurchaseRequestListItemResponse(BaseModel):
    purchase_request_id: UUID
    title: str
    amount_minor: int
    currency: str
    status: str
    current_approval_role: str | None
    created_at: datetime
    updated_at: datetime


class PurchaseRequestListResponse(BaseModel):
    items: list[PurchaseRequestListItemResponse]


class TimelineItemResponse(BaseModel):
    event_type: str
    occurred_at: datetime
    actor_is_current_user: bool
    role_key: str | None
    task_id: UUID | None
    message: str


class TimelineResponse(BaseModel):
    purchase_request_id: UUID
    items: list[TimelineItemResponse]


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
    "",
    response_model=PurchaseRequestListResponse,
    summary="Kendi satın alma taleplerini listele",
    description=(
        "Actor'ın YALNIZ kendi oluşturduğu talepler, en yeni önce. Cursor yerine MVP'de "
        "server-side max page size ile sınırlı (unbounded list YASAK)."
    ),
)
def list_purchase_requests(
    organization_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    membership_query: Annotated[MembershipQuery, Depends(get_membership_query)],
    read_query: Annotated[PurchaseRequestReadQuery, Depends(get_purchase_request_read_query)],
    limit: int = _DEFAULT_PAGE_SIZE,
) -> PurchaseRequestListResponse:
    _require_active_membership(
        membership_query, organization_id=organization_id, user_id=actor.user_id
    )
    bounded = max(1, min(limit, _MAX_PAGE_SIZE))
    items = read_query.list_for_requester(
        tenant_id=organization_id, requester_user_id=actor.user_id, limit=bounded
    )
    return PurchaseRequestListResponse(
        items=[
            PurchaseRequestListItemResponse(
                purchase_request_id=item.purchase_request_id,
                title=item.title,
                amount_minor=item.amount_minor,
                currency=item.currency,
                status=item.status,
                current_approval_role=item.current_approval_role,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ]
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


@router.get(
    "/{purchase_request_id}/timeline",
    response_model=TimelineResponse,
    summary="Satın alma talebinin denetim zaman çizelgesi",
    description=(
        "Talep + onay olaylarının kronolojik, append-only audit timeline'ı. Tenant-scoped "
        "(RLS); hassas değer içermez, kullanıcıya güvenli mesaj döner."
    ),
)
def get_purchase_request_timeline(
    organization_id: UUID,
    purchase_request_id: UUID,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    membership_query: Annotated[MembershipQuery, Depends(get_membership_query)],
    detail_handler: Annotated[GetPurchaseRequestHandler, Depends(get_get_purchase_request_handler)],
    timeline_query: Annotated[AuditTimelineQueryPort, Depends(get_audit_timeline_query)],
) -> TimelineResponse:
    _require_active_membership(
        membership_query, organization_id=organization_id, user_id=actor.user_id
    )
    # Kaynağın (tenant içinde) VARLIĞINI doğrula — yoksa 404 (cross-tenant sızdırmaz).
    detail = detail_handler.handle(
        tenant_id=organization_id,
        purchase_request_id=purchase_request_id,
        current_user_id=actor.user_id,
    )
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    items = timeline_query.list_for_aggregate(
        tenant_id=organization_id,
        aggregate_id=purchase_request_id,
        current_user_id=actor.user_id,
    )
    return TimelineResponse(
        purchase_request_id=purchase_request_id,
        items=[
            TimelineItemResponse(
                event_type=item.event_type,
                occurred_at=item.occurred_at,
                actor_is_current_user=item.actor_is_current_user,
                role_key=item.role_key,
                task_id=item.task_id,
                message=item.message,
            )
            for item in items
        ],
    )
