"""Approval rol atama application hataları (HTTP eşlemesi route'ta).

Domain hatası `InvalidApprovalRoleKeyError` (422) BURADAN re-export edilir; böylece
composition root (route) approval.domain'i doğrudan import etmeden tüm hataları tek
application sınırından yakalar.
"""

from __future__ import annotations

from flowpilot.modules.approval.domain.errors import InvalidApprovalRoleKeyError
from flowpilot.shared.errors import DomainError

__all__ = [
    "ApprovalRoleActorNotMemberError",
    "ApprovalRoleAssignmentConcurrencyError",
    "ApprovalRoleExpectedVersionRequiredError",
    "ApprovalRoleTargetNotActiveError",
    "ApprovalRoleTargetNotFoundError",
    "InvalidApprovalRoleKeyError",
]


class ApprovalRoleActorNotMemberError(DomainError):
    """Actor bu tenant'ta aktif üye değil (→ 404, varlık sızdırmaz)."""


class ApprovalRoleTargetNotFoundError(DomainError):
    """Hedef kullanıcı bu tenant scope'unda üye değil / cross-tenant (→ 404)."""


class ApprovalRoleTargetNotActiveError(DomainError):
    """Hedef üyelik aktif değil (suspended/removed) — atanamaz (→ 409)."""


class ApprovalRoleAssignmentConcurrencyError(DomainError):
    """Optimistic concurrency çakışması / eşzamanlı atama (stale version) (→ 409)."""


class ApprovalRoleExpectedVersionRequiredError(DomainError):
    """Aktif atama var ama expected_version verilmedi (→ 422)."""
