"""Üye yönetimi command/result/view DTO'ları (application sınırı; primitive + UUID).

provider_subject / auth_provider / JWT gibi hassas identity bilgisi DÖNMEZ; yalnız
email_snapshot (null olabilir) döner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class MemberView:
    """Üye listeleme öğesi (removed üyeler durumlarıyla listede kalır)."""

    membership_id: UUID
    user_id: UUID
    email: str | None
    role: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class UpdateMemberCommand:
    tenant_id: UUID
    actor_user_id: UUID
    target_user_id: UUID
    new_role: str | None
    new_status: str | None
    expected_version: int


@dataclass(frozen=True)
class UpdateMemberResult:
    membership_id: UUID
    user_id: UUID
    role: str
    status: str
    version: int
    duplicate: bool
