"""POST /v1/organizations — health dışındaki ilk production endpoint'i.

Kurallar:
- İş mantığı YOK: mevcut CreateOrganization application handler'ı çağrılır;
  transaction burada TEKRAR YAZILMAZ, repository'ye doğrudan ERİŞİLMEZ.
- Actor YALNIZ doğrulanmış `CurrentActor`'dan gelir; request body'de actor ID
  kabul edilmez (bilinmeyen alanlar yok sayılır).
- Tenant header İSTENMEZ — bu endpoint yeni tenant oluşturur (bootstrap).
- Response, transaction commit edildikten SONRA üretilir (handler commit
  başarısızsa exception fırlatır).
- SQLAlchemy modeli değil, Pydantic response modeli döner.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from flowpilot.api.deps import CurrentActor, get_create_organization_handler, get_current_actor
from flowpilot.modules.organization.application.commands import CreateOrganizationCommand
from flowpilot.modules.organization.application.errors import (
    ActorNotFoundError,
    OrganizationNameError,
)
from flowpilot.modules.organization.application.handler import CreateOrganizationHandler

router = APIRouter(prefix="/v1/organizations", tags=["organizations"])


class CreateOrganizationRequest(BaseModel):
    """Organizasyon oluşturma isteği. Bilinmeyen alanlar yok sayılır."""

    name: str = Field(description="Organizasyon görünen adı (1-200 karakter).")


class CreateOrganizationResponse(BaseModel):
    """Başarılı oluşturma yanıtı — source-of-truth transaction commit edilmiştir."""

    organization_id: UUID
    owner_membership_id: UUID
    name: str


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateOrganizationResponse,
    summary="Yeni organizasyon oluştur",
    description=(
        "Doğrulanmış kullanıcı adına yeni bir organizasyon (tenant) ve aktif "
        "owner membership'i AYNI transaction'da oluşturur."
    ),
)
def create_organization(
    body: CreateOrganizationRequest,
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    handler: Annotated[CreateOrganizationHandler, Depends(get_create_organization_handler)],
) -> CreateOrganizationResponse:
    try:
        result = handler.handle(
            CreateOrganizationCommand(
                actor_user_id=actor.user_id,
                organization_name=body.name,
            )
        )
    except OrganizationNameError as exc:
        # Domain doğrulama hatası → 422. Mesaj güvenli, kullanıcıya dönük metindir.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except ActorNotFoundError as exc:
        # Doğrulanmış kimliğe rağmen internal user çözülemedi — kontrollü 401;
        # iç detay sızdırılmaz.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kimlik dogrulanamadi.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return CreateOrganizationResponse(
        organization_id=result.tenant_id,
        owner_membership_id=result.owner_membership_id,
        name=result.organization_name,
    )
