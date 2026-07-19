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


class MembershipQuery(Protocol):
    """Aktif membership sorgusu (authorization gate için).

    Tenant-scoped (RLS): sorgu current tenant context altında çalışır. Yalnız
    `status = active` üyelikler döner; inactive/suspended/removed → None.
    """

    def find_active(self, *, tenant_id: UUID, user_id: UUID) -> ActiveMembershipView | None: ...

    def find_active_owner(self, *, tenant_id: UUID) -> ActiveMembershipView | None:
        """Tenant'ın AKTİF owner üyeliği (default approver assignment için); yoksa None."""
        ...
