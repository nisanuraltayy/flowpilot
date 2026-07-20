"""Invitation aggregate — organizasyon üyelik daveti (FP-E03-001, Dilim A).

Bu dilim yalnız OLUŞTURMA / LİSTELEME / İPTAL kapsar. `accepted` durumu şema ve state
makinesinde tanımlıdır ama KABUL AKIŞI bu dilimde uygulanmaz (Dilim B).

Kurallar (owner-approved, [[ASM-0018]]):
- Rol yalnız `admin` veya `member`; `owner` davetle VERİLEMEZ.
- E-posta trim + lowercase normalize edilir (kimlik değildir; eşleşme sinyali).
- Ham token domain'de tutulmaz — yalnız `token_hash` (SHA-256) taşınır.
- `expires_at` = oluşturma zamanı + 7 gün (sabit).
- `pending → revoked` (idempotent). `accepted` terminaldir; revoke edilemez.

Domain FastAPI/SQLAlchemy/SDK IMPORT ETMEZ (yalnız stdlib + shared).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from flowpilot.modules.organization.domain.membership import MembershipRole
from flowpilot.shared.errors import DomainError
from flowpilot.shared.identifiers import InvitationId, TenantId, UserId

# Owner-approved sabit davet süresi (ASM-0018 (a)).
INVITATION_TTL = timedelta(days=7)

# Davetle atanabilir roller — `owner` bilinçli olarak HARİÇ (ASM-0018 (b)).
INVITABLE_ROLES: frozenset[MembershipRole] = frozenset(
    {MembershipRole.ADMIN, MembershipRole.MEMBER}
)

_MAX_EMAIL_LENGTH = 320


class InvitationStatus(StrEnum):
    """Bir davetin yaşam döngüsü durumu."""

    PENDING = "pending"
    ACCEPTED = "accepted"  # Dilim B; şema/state makinesi bugünden destekler
    REVOKED = "revoked"
    EXPIRED = "expired"


# Yeni davet oluşturmayı ENGELLEMEYEN terminal durumlar (aktif bekleyen değil).
_TERMINAL_STATUSES = frozenset(
    {InvitationStatus.ACCEPTED, InvitationStatus.REVOKED, InvitationStatus.EXPIRED}
)


class InvalidInvitedEmailError(DomainError):
    """Davet e-postası boş veya geçersiz biçimde."""


class InvitationRoleNotAllowedError(DomainError):
    """Davetle verilemeyen rol (owner) veya bilinmeyen rol."""


class InvitationNotRevocableError(DomainError):
    """Davet terminal durumda (accepted); iptal edilemez."""


class InvitationNotAcceptableError(DomainError):
    """Davet bekleyen (pending) değil; kabul edilemez (terminal)."""


def normalize_invited_email(raw_email: str) -> str:
    """E-postayı trim + lowercase normalize eder ve minimal doğrular.

    Kimlik doğrulama YAPMAZ; yalnız güvenli, tutarlı bir eşleşme anahtarı üretir.
    """
    normalized = raw_email.strip().lower()
    if not normalized or len(normalized) > _MAX_EMAIL_LENGTH:
        raise InvalidInvitedEmailError("gecersiz e-posta")
    local, sep, domain = normalized.partition("@")
    if not sep or not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise InvalidInvitedEmailError("gecersiz e-posta")
    return normalized


def invitation_role_from(raw_role: str) -> MembershipRole:
    """String rolü doğrular; yalnız `admin`/`member` kabul, `owner`/bilinmeyen reddedilir."""
    try:
        role = MembershipRole(raw_role.strip().lower())
    except ValueError as exc:
        raise InvitationRoleNotAllowedError("gecersiz rol") from exc
    if role not in INVITABLE_ROLES:
        raise InvitationRoleNotAllowedError("davetle bu rol verilemez")
    return role


@dataclass(frozen=True)
class Invitation:
    """Bir organizasyona (tenant) e-posta ile üyelik daveti.

    `token_hash` yalnız SHA-256 hash'tir; ham token HİÇBİR ZAMAN bu aggregate'te veya
    veritabanında tutulmaz.
    """

    id: InvitationId
    tenant_id: TenantId
    invited_email: str
    role: MembershipRole
    status: InvitationStatus
    token_hash: str
    expires_at: datetime
    invited_by_user_id: UserId
    created_at: datetime
    updated_at: datetime
    version: int
    accepted_by_user_id: UserId | None = None
    accepted_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        id: InvitationId,
        tenant_id: TenantId,
        invited_email: str,
        role: MembershipRole,
        token_hash: str,
        invited_by_user_id: UserId,
        created_at: datetime,
    ) -> Invitation:
        """Yeni `pending` davet üretir. `expires_at` = created_at + 7 gün (sabit).

        Rol yeniden doğrulanır (defense-in-depth): `owner` reddedilir.
        """
        if role not in INVITABLE_ROLES:
            raise InvitationRoleNotAllowedError("davetle bu rol verilemez")
        return cls(
            id=id,
            tenant_id=tenant_id,
            invited_email=normalize_invited_email(invited_email),
            role=role,
            status=InvitationStatus.PENDING,
            token_hash=token_hash,
            expires_at=created_at + INVITATION_TTL,
            invited_by_user_id=invited_by_user_id,
            created_at=created_at,
            updated_at=created_at,
            version=1,
        )

    def is_expired(self, now: datetime) -> bool:
        """Davetin süresi dolmuş mu? (expires_at dahil sınır)."""
        return now >= self.expires_at

    def expire(self, *, now: datetime) -> Invitation:
        """`pending → expired` geçişi (süresi geçmiş bekleyen davet).

        Yalnız `pending` durumdan çağrılır (repo yalnız pending döndürür). `version`
        DEĞİŞMEZ — optimistic CAS beklenen sürüm olarak repo tarafından kullanılır.
        """
        if self.status is not InvitationStatus.PENDING:
            raise InvitationNotRevocableError("yalnız bekleyen davet expired olabilir")
        return replace(self, status=InvitationStatus.EXPIRED, updated_at=now)

    def revoke(self, *, now: datetime) -> Invitation:
        """`pending → revoked` geçişi. Terminal (accepted/revoked/expired) → hata verir.

        Idempotency (zaten revoked/expired) use-case'te ele alınır; burada terminal
        koruması (defense-in-depth). `version` DEĞİŞMEZ — optimistic CAS için repo kullanır.
        """
        if self.status in _TERMINAL_STATUSES:
            raise InvitationNotRevocableError("terminal davet iptal edilemez")
        return replace(self, status=InvitationStatus.REVOKED, updated_at=now)

    def accept(self, *, accepted_by: UserId, now: datetime) -> Invitation:
        """`pending → accepted` geçişi (tek kullanımlık); accepted_by/accepted_at set eder.

        Yalnız `pending` durumdan kabul edilebilir (terminal → hata). Süre kontrolü
        (expiry) use-case'te yapılır; burada durum koruması (defense-in-depth). `version`
        DEĞİŞMEZ — optimistic CAS beklenen sürüm olarak repo tarafından kullanılır.
        """
        if self.status is not InvitationStatus.PENDING:
            raise InvitationNotAcceptableError("yalnız bekleyen davet kabul edilebilir")
        return replace(
            self,
            status=InvitationStatus.ACCEPTED,
            accepted_by_user_id=accepted_by,
            accepted_at=now,
            updated_at=now,
        )
