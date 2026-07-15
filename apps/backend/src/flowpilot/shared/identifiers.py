"""Public identifier value object'leri.

PRD §34.1: Public kimlikler UUID/ULID olmalıdır; sıralı DB ID dışarı açılmaz.
Bu paket hiçbir framework/ORM import etmez — saf domain primitive'leri.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserId:
    """Bir FlowPilot kullanıcısının değişmez iç kimliği."""

    value: UUID


@dataclass(frozen=True, slots=True)
class TenantId:
    """Bir tenant/organization'ın değişmez kimliği."""

    value: UUID


@dataclass(frozen=True, slots=True)
class MembershipId:
    """Bir üyeliğin değişmez kimliği."""

    value: UUID
