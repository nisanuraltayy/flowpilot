"""Membership aggregate ve ilgili enum'lar.

MembershipStatus PRD §9.2'den; MembershipRole tenant seviyesindeki üyelik
rolüdür (RBAC permission kataloğu ayrı `authorization` modülündedir).
Bu aşamada yalnız OWNER/ACTIVE kombinasyonu kullanılır.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from flowpilot.shared.identifiers import MembershipId, TenantId, UserId


class MembershipStatus(StrEnum):
    """Bir üyeliğin yaşam döngüsü durumu (PRD §9.2)."""

    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class MembershipRole(StrEnum):
    """Kullanıcının tenant içindeki üyelik rolü."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


@dataclass(frozen=True)
class Membership:
    """Bir kullanıcının bir tenant içindeki üyeliği."""

    id: MembershipId
    tenant_id: TenantId
    user_id: UserId
    role: MembershipRole
    status: MembershipStatus
    created_at: datetime

    @classmethod
    def create_owner(
        cls,
        *,
        id: MembershipId,
        tenant_id: TenantId,
        user_id: UserId,
        created_at: datetime,
    ) -> Membership:
        """Aktif owner üyeliği oluşturur."""
        return cls(
            id=id,
            tenant_id=tenant_id,
            user_id=user_id,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
            created_at=created_at,
        )
