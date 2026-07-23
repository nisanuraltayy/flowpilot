"""Approval application (use-case) hataları — kontrollü, güvenli.

Domain validation hataları da buradan yeniden dışa verilir; presentation YALNIZ bu
application sınırından yakalar (composition root → domain yasak).
"""

from __future__ import annotations

from flowpilot.modules.approval.domain.errors import (
    InvalidApprovalCommentError,
    InvalidApprovalDecisionError,
)
from flowpilot.shared.errors import DomainError


class ApprovalMembershipNotActiveError(DomainError):
    """Actor bu tenant'ta aktif üye değil — tenant/kaynak varlığı sızdırılmaz (404)."""


class ApprovalTaskNotAssignedError(DomainError):
    """Task actor'a atanmamış — varlık sızdırılmaz (404)."""


class ActiveOwnerNotFoundError(DomainError):
    """Default assignment için aktif owner bulunamadı (kontrollü configuration error)."""


class DuplicateDecisionConflictError(DomainError):
    """Aynı idempotency key farklı payload ile geldi VEYA task zaten kararlaştırıldı (409)."""


class SelfApprovalConflictError(DomainError):
    """Talep sahibi kendi talebindeki adımı sonuçlandıramaz — güvenli conflict (409)."""


__all__ = [
    "ActiveOwnerNotFoundError",
    "ApprovalMembershipNotActiveError",
    "ApprovalTaskNotAssignedError",
    "DuplicateDecisionConflictError",
    "InvalidApprovalCommentError",
    "InvalidApprovalDecisionError",
    "SelfApprovalConflictError",
]
