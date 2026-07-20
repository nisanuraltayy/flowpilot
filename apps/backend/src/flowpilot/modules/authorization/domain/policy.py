"""Rol → permission kararı (saf, deterministik, test edilebilir).

Membership rolleri (organization.MembershipRole değerleri): `owner`, `admin`, `member`.
Bu dilimde davet yönetimi YALNIZ `owner`/`admin`'e açıktır; `member` yasaktır. Aktif
olmayan üyelik (find_active None döner) buraya ULAŞMADAN reddedilir — bu policy yalnız
AKTİF membership rolüyle çağrılır.

Not: Bu, org-yönetişim rolü (owner/admin/member) hakkındadır; workflow approval role_key
(team_manager/finance/general_manager) AYRI bir kavramdır ve buraya karışmaz.
"""

from __future__ import annotations

from flowpilot.modules.authorization.domain.permissions import Permission

_INVITATION_MANAGEMENT: frozenset[Permission] = frozenset(
    {
        Permission.ORGANIZATION_INVITATION_CREATE,
        Permission.ORGANIZATION_INVITATION_READ,
        Permission.ORGANIZATION_INVITATION_REVOKE,
    }
)

# Merkezi katalog: rol → izin kümesi. Bilinmeyen/eksik rol → boş küme (deny).
_ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "owner": _INVITATION_MANAGEMENT,
    "admin": _INVITATION_MANAGEMENT,
    "member": frozenset(),
}


def permissions_for_role(role: str) -> frozenset[Permission]:
    """Verilen membership rolünün sahip olduğu izin kümesi (bilinmeyen → boş)."""
    return _ROLE_PERMISSIONS.get(role, frozenset())


def is_authorized(*, role: str, permission: Permission) -> bool:
    """Rol, istenen permission'a sahip mi?"""
    return permission in permissions_for_role(role)
