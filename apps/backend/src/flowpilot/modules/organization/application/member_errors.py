"""Üye yönetimi application hataları (HTTP eşlemesi route'ta).

Domain hataları (removed-terminal, invalid transition, forbidden target) BURADAN
re-export edilir; böylece composition root (route) organization.domain'i doğrudan import
etmeden tüm hataları tek application sınırından yakalar.
"""

from __future__ import annotations

from flowpilot.modules.organization.domain.member_management_policy import (
    MemberManagementForbiddenError,
)
from flowpilot.modules.organization.domain.membership import (
    InvalidMembershipTransitionError,
    MembershipRemovedError,
)
from flowpilot.shared.errors import DomainError

__all__ = [
    "ApprovalResponsibilityConflictError",
    "FinalOwnerError",
    "InvalidMemberUpdateError",
    "InvalidMembershipTransitionError",
    "MemberActorNotMemberError",
    "MemberManagementForbiddenError",
    "MemberNotFoundError",
    "MemberSelfMutationError",
    "MembershipConcurrencyError",
    "MembershipRemovedError",
]


class MemberActorNotMemberError(DomainError):
    """Actor bu tenant'ta aktif üye değil (→ 404, varlık sızdırmaz)."""


class MemberNotFoundError(DomainError):
    """Hedef üyelik bu tenant scope'unda bulunamadı / cross-tenant (→ 404)."""


class MemberSelfMutationError(DomainError):
    """Kullanıcı kendi rol/status/üyeliğini değiştiremez (→ 409)."""


class FinalOwnerError(DomainError):
    """Son aktif owner düşürülemez/suspend/remove edilemez (→ 409)."""


class ApprovalResponsibilityConflictError(DomainError):
    """Kullanıcının aktif onay sorumluluğu var; önce yeniden atanmalı (→ 409)."""


class MembershipConcurrencyError(DomainError):
    """Optimistic concurrency çakışması (stale expected_version) (→ 409)."""


class InvalidMemberUpdateError(DomainError):
    """Geçersiz rol/status değeri veya role+status ikisi de eksik (→ 422)."""
