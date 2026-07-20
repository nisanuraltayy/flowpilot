"""Permission kataloğu — merkezi, string-stabil izin anahtarları (FF-14).

Yeni permission'lar buraya EKLENİR; kod içinde ham string karşılaştırması yapılmaz.
Bu dilim (FP-E03-001) yalnız davet yönetimi permission'larını tanımlar.
"""

from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    """Sistemdeki korumalı aksiyonların stabil anahtarları."""

    ORGANIZATION_INVITATION_CREATE = "organization.invitation.create"
    ORGANIZATION_INVITATION_READ = "organization.invitation.read"
    ORGANIZATION_INVITATION_REVOKE = "organization.invitation.revoke"
    ORGANIZATION_MEMBER_READ = "organization.member.read"
    ORGANIZATION_MEMBER_ROLE_CHANGE = "organization.member.role.change"
    ORGANIZATION_MEMBER_SUSPEND = "organization.member.suspend"
    ORGANIZATION_MEMBER_REACTIVATE = "organization.member.reactivate"
    ORGANIZATION_MEMBER_REMOVE = "organization.member.remove"
