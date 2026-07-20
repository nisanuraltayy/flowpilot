"""Approval domain: role assignment, decision, comment.

Invariant'lar (owner kararı + güvenlik):
- tenant + role key için YALNIZ BİR aktif assignee (DB partial-unique + burada).
- Aynı kullanıcı birden fazla role atanabilir.
- ApprovalDecision IMMUTABLE'dır (append-only).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from flowpilot.modules.approval.domain.enums import ApprovalDecisionType, ApprovalRoleKey
from flowpilot.modules.approval.domain.errors import InvalidApprovalCommentError
from flowpilot.shared.identifiers import TenantId, UserId

COMMENT_MAX_LENGTH = 2000


@dataclass(frozen=True, slots=True)
class ApprovalRoleAssignmentId:
    value: UUID


@dataclass(frozen=True, slots=True)
class ApprovalDecisionId:
    value: UUID


class ApprovalAssignmentStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class ApprovalComment:
    """Opsiyonel yorum; verilirse ≤ 2000 karakter (boş → None)."""

    value: str | None

    def __init__(self, raw: str | None) -> None:
        if raw is None:
            object.__setattr__(self, "value", None)
            return
        trimmed = raw.strip()
        if not trimmed:
            object.__setattr__(self, "value", None)
            return
        if len(trimmed) > COMMENT_MAX_LENGTH:
            raise InvalidApprovalCommentError(
                f"yorum en çok {COMMENT_MAX_LENGTH} karakter olabilir"
            )
        object.__setattr__(self, "value", trimmed)


@dataclass(frozen=True)
class ApprovalRoleAssignment:
    """Bir tenant içinde bir role key'e atanmış aktif kullanıcı.

    `version` optimistic concurrency içindir ve role_key başına AKTİF atamada MONOTONİK
    ilerler: reassign sırasında yeni active satır `version = önceki_active.version + 1`
    alır (ilk atama = 1). Böylece eş zamanlı bir stale reassign temiz biçimde reddedilir.
    """

    id: ApprovalRoleAssignmentId
    tenant_id: TenantId
    role_key: ApprovalRoleKey
    assigned_user_id: UserId
    status: ApprovalAssignmentStatus
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create_active(
        cls,
        *,
        id: ApprovalRoleAssignmentId,
        tenant_id: TenantId,
        role_key: ApprovalRoleKey,
        assigned_user_id: UserId,
        created_at: datetime,
        version: int = 1,
    ) -> ApprovalRoleAssignment:
        return cls(
            id=id,
            tenant_id=tenant_id,
            role_key=role_key,
            assigned_user_id=assigned_user_id,
            status=ApprovalAssignmentStatus.ACTIVE,
            version=version,
            created_at=created_at,
            updated_at=created_at,
        )


@dataclass(frozen=True)
class ApprovalDecision:
    """Immutable onay kararı kaydı (append-only)."""

    id: ApprovalDecisionId
    tenant_id: TenantId
    task_id: UUID
    actor_user_id: UserId
    decision: ApprovalDecisionType
    comment: ApprovalComment
    idempotency_key: str
    request_fingerprint: str
    created_at: datetime
