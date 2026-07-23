"""Blocked approval task çözümleme application hataları (HTTP eşlemesi route'ta)."""

from __future__ import annotations

from flowpilot.shared.errors import DomainError

__all__ = [
    "BlockedTaskActorNotMemberError",
    "BlockedTaskNotFoundError",
    "BlockedTaskResolveConflictError",
]


class BlockedTaskActorNotMemberError(DomainError):
    """Actor bu tenant'ta aktif üye değil (→ 404, varlık sızdırmaz)."""


class BlockedTaskNotFoundError(DomainError):
    """Task bu tenant scope'unda yok / cross-tenant (→ 404)."""


class BlockedTaskResolveConflictError(DomainError):
    """Çözümleme yapılamadı (→ 409): task self-approval nedeniyle blocked değil, uygun
    active role assignment yok, aday requester ya da aktif üye değil, stale/terminal."""
