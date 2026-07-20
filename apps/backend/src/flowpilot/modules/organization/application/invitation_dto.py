"""Invitation use-case command/result DTO'ları (application sınırı; primitive + UUID).

Ham token YALNIZ `CreateInvitationResult.raw_token` alanında ve YALNIZ ilk oluşturmada
bulunur (idempotent replay'de `None`). Liste/revoke DTO'larında token/token_hash YOKTUR.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class CreateInvitationCommand:
    tenant_id: UUID
    actor_user_id: UUID
    invited_email: str
    role: str
    idempotency_key: str | None = None


@dataclass(frozen=True)
class CreateInvitationResult:
    invitation_id: UUID
    invited_email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime
    # raw_token/accept_url YALNIZ ilk oluşturmada doludur; idempotent replay'de None.
    raw_token: str | None
    accept_url: str | None
    duplicate: bool


@dataclass(frozen=True)
class PendingInvitationView:
    """Bekleyen (pending + süresi dolmamış) davetin token'sız salt-okunur özeti."""

    invitation_id: UUID
    invited_email: str
    role: str
    status: str
    expires_at: datetime
    invited_by_user_id: UUID
    created_at: datetime


@dataclass(frozen=True)
class RevokeInvitationCommand:
    tenant_id: UUID
    actor_user_id: UUID
    invitation_id: UUID


@dataclass(frozen=True)
class RevokeInvitationResult:
    invitation_id: UUID
    status: str
    duplicate: bool
