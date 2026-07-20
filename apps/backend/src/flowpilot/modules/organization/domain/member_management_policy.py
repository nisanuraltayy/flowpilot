"""Üye yönetimi hedef-yetki policy'si (actor rolü × hedef üyelik) — saf domain.

Merkezi authorization coarse gate'ini (owner/admin yönetebilir, member yasak) TAMAMLAR;
burada HEDEFE göre ince yetki: admin yalnız member hedefleri yönetir ve owner rolü veremez;
owner her hedefi yönetebilir (final-owner invariant'ı use-case'te kontrol edilir).

Framework/ORM importu YOK.
"""

from __future__ import annotations

from flowpilot.modules.organization.domain.membership import MembershipRole
from flowpilot.shared.errors import DomainError


class MemberManagementForbiddenError(DomainError):
    """Actor bu HEDEF üzerinde bu değişikliği yapmaya yetkili değil (→ 403)."""


def authorize_member_change(
    *,
    actor_role: str,
    target_role: MembershipRole,
    new_role: MembershipRole | None,
) -> None:
    """Actor'ın hedef üyeliğe istenen rol değişikliğini yapmaya yetkili olduğunu doğrular.

    owner: her hedef (final-owner invariant ayrıca kontrol edilir).
    admin: YALNIZ `member` hedefler; owner rolü VEREMEZ; owner/admin hedeflere dokunamaz.
    Aksi → `MemberManagementForbiddenError` (403).
    """
    if actor_role == MembershipRole.OWNER.value:
        return
    if actor_role == MembershipRole.ADMIN.value:
        if target_role is not MembershipRole.MEMBER:
            raise MemberManagementForbiddenError("admin yalnız member hedefleri yönetebilir")
        if new_role is MembershipRole.OWNER:
            raise MemberManagementForbiddenError("admin owner rolü veremez")
        return
    # member/bilinmeyen — coarse authz'den geçmemeli; savunma amaçlı reddet.
    raise MemberManagementForbiddenError("üye yönetimi için yetkisiz")
