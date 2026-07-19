"""GET /v1/me/organizations — doğrulanmış kullanıcının aktif organizasyonları.

Frontend'in yeniden girişte aktif organizasyon context'ini çözebilmesi için minimal
read endpoint'i. Bu bir organization MANAGEMENT API'si DEĞİLDİR.

Kurallar:
- İş mantığı YOK: organization application query contract'ı (`MembershipQuery`)
  çağrılır; route organization infrastructure tablosuna DOĞRUDAN erişmez.
- Actor YALNIZ doğrulanmış `CurrentActor`'dan gelir.
- Yalnız actor'ın KENDİ aktif üyelikleri döner (actor-scoped RLS; migration 0006).
- SQLAlchemy modeli değil, Pydantic response modeli döner.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from flowpilot.api.deps import CurrentActor, get_current_actor, get_membership_query
from flowpilot.modules.organization.application.contracts import MembershipQuery

router = APIRouter(prefix="/v1/me", tags=["me"])


class MyOrganizationItem(BaseModel):
    organization_id: UUID
    name: str
    membership_kind: str
    membership_status: str


class MyOrganizationsResponse(BaseModel):
    items: list[MyOrganizationItem]


@router.get(
    "/organizations",
    response_model=MyOrganizationsResponse,
    summary="Kullanıcının aktif organizasyonları",
    description=(
        "Doğrulanmış kullanıcının AKTİF üye olduğu organizasyonları döndürür (context "
        "çözümü için). Başka kullanıcının üyelikleri görünmez. Organization management "
        "API'si değildir."
    ),
)
def list_my_organizations(
    actor: Annotated[CurrentActor, Depends(get_current_actor)],
    membership_query: Annotated[MembershipQuery, Depends(get_membership_query)],
) -> MyOrganizationsResponse:
    organizations = membership_query.list_active_for_user(user_id=actor.user_id)
    return MyOrganizationsResponse(
        items=[
            MyOrganizationItem(
                organization_id=org.organization_id,
                name=org.name,
                membership_kind=org.membership_kind,
                membership_status=org.membership_status,
            )
            for org in organizations
        ]
    )
