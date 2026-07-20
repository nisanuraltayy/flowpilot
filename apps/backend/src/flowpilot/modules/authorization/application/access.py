"""Merkezi yetki sınırının DIŞA sunulan API'si.

Başka bounded context'ler (ör. organization) YALNIZ buradan yetki sorar; authorization
domain'ini DOĞRUDAN import etmez (dependency-rules §2 — cross-context application importu
serbest, domain/infrastructure importu YASAK).

Kullanım:
    from flowpilot.modules.authorization.application.access import Permission, ensure_permitted
    ensure_permitted(role=membership.role, permission=Permission.ORGANIZATION_INVITATION_CREATE)
"""

from __future__ import annotations

from flowpilot.modules.authorization.application.errors import PermissionDeniedError
from flowpilot.modules.authorization.domain.permissions import Permission
from flowpilot.modules.authorization.domain.policy import is_authorized, permissions_for_role

__all__ = [
    "Permission",
    "PermissionDeniedError",
    "ensure_permitted",
    "is_authorized",
    "permissions_for_role",
]


def ensure_permitted(*, role: str, permission: Permission) -> None:
    """Rol yetkili değilse `PermissionDeniedError` fırlatır (yetkiliyse sessiz döner)."""
    if not is_authorized(role=role, permission=permission):
        raise PermissionDeniedError(f"'{role}' rolu '{permission.value}' islemine yetkili degil")
