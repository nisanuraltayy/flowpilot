"""Organization (Tenant) aggregate'i.

Bir Organization aynı zamanda tenant sınırıdır. `created_by`, RLS insert
policy'sinin dayandığı actor'dür: bir kullanıcı yalnız KENDİ adına organizasyon
oluşturabilir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from flowpilot.modules.organization.domain.organization_name import OrganizationName
from flowpilot.shared.identifiers import TenantId, UserId


class OrganizationStatus(StrEnum):
    """Tenant yaşam döngüsü durumu (PRD §9.1)."""

    ACTIVE = "active"
    SCHEDULED_FOR_DELETION = "scheduled_for_deletion"


@dataclass(frozen=True)
class Organization:
    """Bir tenant/organization."""

    id: TenantId
    name: OrganizationName
    created_by: UserId
    created_at: datetime
    status: OrganizationStatus = OrganizationStatus.ACTIVE

    @classmethod
    def create(
        cls,
        *,
        id: TenantId,
        name: OrganizationName,
        created_by: UserId,
        created_at: datetime,
    ) -> Organization:
        """Aktif bir organizasyon oluşturur."""
        return cls(id=id, name=name, created_by=created_by, created_at=created_at)
