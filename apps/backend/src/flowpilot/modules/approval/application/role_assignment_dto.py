"""Approval rol atama command/result/view DTO'ları (application sınırı; primitive + UUID).

Hassas identity (provider_subject / auth_provider / JWT) DÖNMEZ; yalnız email_snapshot
(null olabilir) döner. Governance rolü (owner/admin/member) ile approval role_key
(team_manager/finance/general_manager) AYRIDIR.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class ApprovalRoleAssignmentView:
    """Rol atama listeleme öğesi (aktif atama)."""

    assignment_id: UUID
    role_key: str
    assigned_user_id: UUID
    assigned_user_email: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TargetMembershipInfo:
    """Hedef kullanıcının tenant içindeki üyelik durumu + email (cross-module read)."""

    status: str
    email: str | None


@dataclass(frozen=True)
class AssignApprovalRoleCommand:
    tenant_id: UUID
    actor_user_id: UUID
    role_key: str
    target_user_id: UUID
    expected_version: int | None


@dataclass(frozen=True)
class AssignApprovalRoleResult:
    assignment_id: UUID
    role_key: str
    assigned_user_id: UUID
    assigned_user_email: str | None
    status: str
    version: int
    duplicate: bool
