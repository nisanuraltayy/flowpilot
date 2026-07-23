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

# Üye yönetimi coarse gate: owner/admin YÖNETEBİLİR (hedefe göre ince yetki organization
# domain policy'sinde); member YÖNETEMEZ. read/role/suspend/reactivate/remove.
_MEMBER_MANAGEMENT: frozenset[Permission] = frozenset(
    {
        Permission.ORGANIZATION_MEMBER_READ,
        Permission.ORGANIZATION_MEMBER_ROLE_CHANGE,
        Permission.ORGANIZATION_MEMBER_SUSPEND,
        Permission.ORGANIZATION_MEMBER_REACTIVATE,
        Permission.ORGANIZATION_MEMBER_REMOVE,
    }
)

# Workflow approval rol atama coarse gate: owner/admin okuyabilir ve değiştirebilir;
# member yasak. Bu, org-yönetişim rolünden ayrı bir kavramdır (approval role_key).
_APPROVAL_ROLE_MANAGEMENT: frozenset[Permission] = frozenset(
    {
        Permission.APPROVAL_ROLE_ASSIGNMENT_READ,
        Permission.APPROVAL_ROLE_ASSIGNMENT_CHANGE,
    }
)

# Self-approval nedeniyle blocked task'ları görme + güvenli çözümleme: owner/admin.
_BLOCKED_TASK_MANAGEMENT: frozenset[Permission] = frozenset(
    {
        Permission.APPROVAL_BLOCKED_TASK_READ,
        Permission.APPROVAL_BLOCKED_TASK_RESOLVE,
    }
)

_OWNER_ADMIN: frozenset[Permission] = (
    _INVITATION_MANAGEMENT
    | _MEMBER_MANAGEMENT
    | _APPROVAL_ROLE_MANAGEMENT
    | _BLOCKED_TASK_MANAGEMENT
)

# Merkezi katalog: rol → izin kümesi. Bilinmeyen/eksik rol → boş küme (deny).
_ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "owner": _OWNER_ADMIN,
    "admin": _OWNER_ADMIN,
    "member": frozenset(),
}


def permissions_for_role(role: str) -> frozenset[Permission]:
    """Verilen membership rolünün sahip olduğu izin kümesi (bilinmeyen → boş)."""
    return _ROLE_PERMISSIONS.get(role, frozenset())


def is_authorized(*, role: str, permission: Permission) -> bool:
    """Rol, istenen permission'a sahip mi?"""
    return permission in permissions_for_role(role)
