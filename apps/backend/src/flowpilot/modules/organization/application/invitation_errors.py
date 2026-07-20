"""Invitation use-case application hataları (HTTP eşlemesi route'ta yapılır).

Domain doğrulama hataları BURADAN re-export edilir; böylece composition root (route)
organization.domain'i DOĞRUDAN import etmeden tüm invitation hatalarını tek application
sınırından yakalar (dependency-rules §2, check_import_boundaries kural 3).
"""

from __future__ import annotations

from flowpilot.modules.organization.domain.invitation import (
    InvalidInvitedEmailError,
    InvitationNotRevocableError,
    InvitationRoleNotAllowedError,
)
from flowpilot.shared.errors import DomainError

__all__ = [
    "AlreadyActiveMemberError",
    "DuplicatePendingInvitationError",
    "IdempotencyKeyReuseError",
    "InvalidInvitedEmailError",
    "InvitationActorNotMemberError",
    "InvitationConcurrencyError",
    "InvitationNotFoundError",
    "InvitationNotRevocableError",
    "InvitationRoleNotAllowedError",
]


class InvitationActorNotMemberError(DomainError):
    """Actor bu tenant'ta aktif üye değil (→ 404, varlık sızdırmaz)."""


class InvitationNotFoundError(DomainError):
    """Davet bu tenant scope'unda bulunamadı / cross-tenant (→ 404)."""


class AlreadyActiveMemberError(DomainError):
    """Davet edilen e-posta bu tenant'ta zaten aktif üye (→ 409)."""


class DuplicatePendingInvitationError(DomainError):
    """Bu tenant + e-posta için zaten aktif bir bekleyen davet var (→ 409)."""


class IdempotencyKeyReuseError(DomainError):
    """Aynı Idempotency-Key farklı payload ile yeniden kullanıldı (→ 409)."""


class InvitationConcurrencyError(DomainError):
    """Optimistic concurrency çakışması (stale version) (→ 409)."""
