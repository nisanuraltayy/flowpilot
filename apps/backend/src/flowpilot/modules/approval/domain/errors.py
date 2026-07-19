"""Approval domain error'ları (kontrollü, crash değil)."""

from __future__ import annotations

from flowpilot.shared.errors import DomainError


class ApprovalError(DomainError):
    """Tüm approval domain hatalarının tabanı."""


class InvalidApprovalRoleKeyError(ApprovalError):
    """Rol anahtarı allow-list dışında."""


class InvalidApprovalDecisionError(ApprovalError):
    """Karar tipi approve/reject dışında."""


class InvalidApprovalCommentError(ApprovalError):
    """Yorum üst sınırı aşıyor."""
