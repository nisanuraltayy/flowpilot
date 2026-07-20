"""Invitation application port'ları (aggregate-specific; generic repository YASAK).

`InvitationUnitOfWork` tek transaction + RLS context + audit yazımını birleştirir.
`audit` alanı audit'in application contract'ıdır (`AuditWriterPort`) — cross-module
application importu serbest; audit domain/infrastructure DOĞRUDAN import EDİLMEZ.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from flowpilot.modules.audit.application.ports import AuditWriterPort
from flowpilot.modules.organization.application.invitation_dto import PendingInvitationView
from flowpilot.modules.organization.domain.invitation import Invitation
from flowpilot.modules.organization.domain.membership import Membership


@dataclass(frozen=True)
class StoredInvitation:
    """Idempotency lookup sonucu: davet + saklanan request fingerprint."""

    invitation: Invitation
    request_fingerprint: str | None


@dataclass(frozen=True)
class MembershipRecord:
    """Bir üyeliğin salt-okunur özeti (herhangi bir status)."""

    membership_id: UUID
    role: str
    status: str


@dataclass(frozen=True)
class InvitationPreviewRow:
    """Davet önizleme read model satırı (token/e-posta içermez)."""

    organization_id: UUID
    organization_name: str
    role: str
    status: str
    expires_at: datetime


class InvitationRepository(Protocol):
    """Invitation aggregate yazma/okuma port'u (organization-owned tablo)."""

    def add(
        self,
        invitation: Invitation,
        *,
        idempotency_key: str | None,
        request_fingerprint: str | None,
    ) -> None: ...

    def update_checked(self, invitation: Invitation, *, expected_version: int) -> None:
        """Optimistic CAS ile günceller; stale version → `InvitationConcurrencyError`."""
        ...

    def find_by_id(self, *, tenant_id: UUID, invitation_id: UUID) -> Invitation | None: ...

    def find_by_token_hash(self, *, tenant_id: UUID, token_hash: str) -> Invitation | None:
        """Tenant scope'unda token_hash ile davet (kabul/önizleme lookup'ı)."""
        ...

    def find_pending_by_email(self, *, tenant_id: UUID, invited_email: str) -> Invitation | None:
        """`status='pending'` davet varsa döner (SÜRE FİLTRESİ YOK).

        Süresi dolmuş olup olmadığı use-case'te `is_expired(now)` ile belirlenir:
        süresi geçmişse expired'a geçirilip yeniden davete izin verilir. Partial unique
        (status='pending') gereği en fazla bir satır döner.
        """
        ...

    def find_by_idempotency_key(
        self, *, tenant_id: UUID, idempotency_key: str
    ) -> StoredInvitation | None: ...


class MembershipWriteRepository(Protocol):
    """Kabul akışı için üyelik yazma/okuma (aynı transaction; tenant-scoped RLS)."""

    def add(self, membership: Membership) -> None: ...

    def find_by_user(self, *, tenant_id: UUID, user_id: UUID) -> MembershipRecord | None:
        """Tenant + user için üyeliği (HERHANGİ status) döner; yoksa None."""
        ...


class InvitationUnitOfWork(Protocol):
    """Tek transaction + RLS context + audit (compose; wiring'de kurulur)."""

    invitations: InvitationRepository
    audit: AuditWriterPort

    def __enter__(self) -> InvitationUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def set_actor_context(self, actor_user_id: UUID) -> None: ...

    def set_tenant_context(self, tenant_id: UUID) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class InvitationAcceptUnitOfWork(Protocol):
    """Davet kabulü tek transaction: invitation + membership + audit (wiring'de compose).

    Kabul + üyelik oluşturma + audit AYNI transaction'da commit edilir; başarısızlıkta
    yarım üyelik veya yarım accepted davet KALMAZ.
    """

    invitations: InvitationRepository
    memberships: MembershipWriteRepository
    audit: AuditWriterPort

    def __enter__(self) -> InvitationAcceptUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def set_actor_context(self, actor_user_id: UUID) -> None: ...

    def set_tenant_context(self, tenant_id: UUID) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class InvitationQuery(Protocol):
    """Bekleyen davetleri listeleyen salt-okunur read model (tenant-scoped, RLS)."""

    def list_pending(
        self, *, tenant_id: UUID, now: datetime, limit: int
    ) -> list[PendingInvitationView]: ...


class InvitationPreviewQuery(Protocol):
    """Davet önizleme read model (auth'suz; tenant-scoped, RLS). Token/e-posta döndürmez."""

    def find(self, *, tenant_id: UUID, token_hash: str) -> InvitationPreviewRow | None: ...


class InvitationAcceptUrlBuilder(Protocol):
    """Ham token'dan gelecekteki kabul URL'ini üreten port (base URL config'ten).

    Hard-coded host YAZMAZ; base URL yoksa relative path döner (proje config kuralı).
    """

    def build(self, *, tenant_id: UUID, raw_token: str) -> str: ...
