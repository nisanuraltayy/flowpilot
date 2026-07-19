"""Organization'ın DIŞARI SUNDUĞU cross-module read contract'ları.

Başka modüller (ör. purchase_request) organization verisine YALNIZ bu açık
application query'leri üzerinden erişir — organization domain/infrastructure
katmanını doğrudan import etmez (dependency-rules §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class ActiveMembershipView:
    """Bir kullanıcının bir tenant içindeki AKTİF üyeliğinin salt-okunur özeti."""

    membership_id: UUID
    tenant_id: UUID
    user_id: UUID
    role: str


@dataclass(frozen=True)
class UserOrganizationView:
    """Bir kullanıcının AKTİF üye olduğu bir organizasyonun görünen özeti.

    Frontend'in yeniden girişte aktif org context'ini çözmesi için (org adı dâhil).
    """

    organization_id: UUID
    name: str
    membership_kind: str
    membership_status: str


class MembershipQuery(Protocol):
    """Aktif membership sorgusu (authorization gate için).

    Tenant-scoped (RLS): sorgu current tenant context altında çalışır. Yalnız
    `status = active` üyelikler döner; inactive/suspended/removed → None.
    """

    def find_active(self, *, tenant_id: UUID, user_id: UUID) -> ActiveMembershipView | None: ...

    def find_active_owner(self, *, tenant_id: UUID) -> ActiveMembershipView | None:
        """Tenant'ın AKTİF owner üyeliği (default approver assignment için); yoksa None."""
        ...

    def list_active_for_user(self, *, user_id: UUID) -> list[UserOrganizationView]:
        """Kullanıcının AKTİF üye olduğu organizasyonlar (org adı ile), cross-tenant.

        Actor-scoped RLS policy (migration 0006) ile YALNIZ kullanıcının kendi üyelik
        satırları döner; başka kullanıcının üyeliği görünmez. Üyelik yoksa boş liste.
        """
        ...
