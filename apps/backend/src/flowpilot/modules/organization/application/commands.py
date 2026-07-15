"""CreateOrganization command ve result — açık application contract'ları."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CreateOrganizationCommand:
    """Bir kullanıcının organizasyon oluşturma isteği."""

    actor_user_id: UUID
    organization_name: str


@dataclass(frozen=True)
class CreateOrganizationResult:
    """Başarılı oluşturmanın sonucu."""

    tenant_id: UUID
    owner_membership_id: UUID
