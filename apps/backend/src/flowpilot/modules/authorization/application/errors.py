"""authorization application hataları."""

from __future__ import annotations

from flowpilot.shared.errors import DomainError


class PermissionDeniedError(DomainError):
    """Aktif üye ancak istenen aksiyona yetkisiz (→ HTTP 403)."""
