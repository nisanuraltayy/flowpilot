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
    # Workflow approval rol atamaları (team_manager/finance/general_manager) — gerçek
    # kullanıcılara atama. Bu, org-yönetişim rolünden (owner/admin/member) AYRIDIR.
    APPROVAL_ROLE_ASSIGNMENT_READ = "approval.role_assignment.read"
    APPROVAL_ROLE_ASSIGNMENT_CHANGE = "approval.role_assignment.change"
    # Self-approval nedeniyle blocked kalan approval task'ları görme + güvenli çözümleme.
    APPROVAL_BLOCKED_TASK_READ = "approval.blocked_task.read"
    APPROVAL_BLOCKED_TASK_RESOLVE = "approval.blocked_task.resolve"
