"""Membership aggregate ve ilgili enum'lar.

MembershipStatus PRD §9.2'den; MembershipRole tenant seviyesindeki üyelik rolüdür
(RBAC permission kataloğu ayrı `authorization` modülündedir). Üye yönetimi (FP-E03-002):
rol/status geçişleri, `removed` terminal, optimistic concurrency (`version`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from flowpilot.shared.errors import DomainError
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


# İzin verilen status geçişleri (owner-approved). `removed` TERMİNALdir.
_ALLOWED_STATUS_TRANSITIONS: dict[MembershipStatus, frozenset[MembershipStatus]] = {
    MembershipStatus.ACTIVE: frozenset({MembershipStatus.SUSPENDED, MembershipStatus.REMOVED}),
    MembershipStatus.SUSPENDED: frozenset({MembershipStatus.ACTIVE, MembershipStatus.REMOVED}),
    MembershipStatus.INVITED: frozenset({MembershipStatus.ACTIVE, MembershipStatus.REMOVED}),
    MembershipStatus.REMOVED: frozenset(),
}


class MembershipRemovedError(DomainError):
    """`removed` üyelik terminaldir; rolü/durumu değiştirilemez."""


class InvalidMembershipTransitionError(DomainError):
    """Geçersiz status geçişi (izin verilmeyen kaynak→hedef)."""


@dataclass(frozen=True)
class Membership:
    """Bir kullanıcının bir tenant içindeki üyeliği."""

    id: MembershipId
    tenant_id: TenantId
    user_id: UserId
    role: MembershipRole
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime
    version: int

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
            updated_at=created_at,
            version=1,
        )

    @classmethod
    def create_active(
        cls,
        *,
        id: MembershipId,
        tenant_id: TenantId,
        user_id: UserId,
        role: MembershipRole,
        created_at: datetime,
    ) -> Membership:
        """Verilen rolle AKTİF üyelik oluşturur (davet kabulünde kullanılır).

        `owner` bu yolla ATANAMAZ — davetle yalnız admin/member verilir; owner koruması
        çağıran (davet kabulü) tarafında da uygulanır, burada da savunma amaçlı reddedilir.
        """
        if role is MembershipRole.OWNER:
            raise ValueError("owner rolü davet kabulüyle atanamaz")
        return cls(
            id=id,
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            status=MembershipStatus.ACTIVE,
            created_at=created_at,
            updated_at=created_at,
            version=1,
        )

    # --- üye yönetimi geçişleri (FP-E03-002) --------------------------------

    def is_active_owner(self) -> bool:
        return self.role is MembershipRole.OWNER and self.status is MembershipStatus.ACTIVE

    def deactivates_owner(
        self, *, new_role: MembershipRole | None, new_status: MembershipStatus | None
    ) -> bool:
        """Bu değişiklik AKTİF bir owner'ı owner-havuzundan çıkarır mı? (final-owner kontrolü)."""
        if not self.is_active_owner():
            return False
        role_demote = new_role is not None and new_role is not MembershipRole.OWNER
        status_deactivate = new_status is not None and new_status in (
            MembershipStatus.SUSPENDED,
            MembershipStatus.REMOVED,
        )
        return role_demote or status_deactivate

    def apply_management_change(
        self,
        *,
        new_role: MembershipRole | None,
        new_status: MembershipStatus | None,
        now: datetime,
    ) -> Membership:
        """Rol ve/veya status değişikliğini uygular (geçiş kurallarını doğrular).

        `removed` üyeliğe hiçbir değişiklik uygulanamaz. Status geçişi izin listesine tabidir.
        `version` DEĞİŞMEZ — optimistic CAS beklenen sürüm olarak repo tarafından kullanılır.
        """
        if self.status is MembershipStatus.REMOVED:
            raise MembershipRemovedError("kaldırılmış üyelik değiştirilemez")

        target_role = new_role if new_role is not None else self.role
        target_status: MembershipStatus = self.status
        if new_status is not None and new_status is not self.status:
            if new_status not in _ALLOWED_STATUS_TRANSITIONS[self.status]:
                raise InvalidMembershipTransitionError(
                    f"geçersiz status geçişi: {self.status.value} → {new_status.value}"
                )
            target_status = new_status

        return replace(self, role=target_role, status=target_status, updated_at=now)

    def is_noop(
        self, *, new_role: MembershipRole | None, new_status: MembershipStatus | None
    ) -> bool:
        """İstenen (role, status) mevcut değerlerle aynı mı? (idempotent no-op)."""
        role_same = new_role is None or new_role is self.role
        status_same = new_status is None or new_status is self.status
        return role_same and status_same
