"""Invitation use-case testleri için deterministik in-memory fake'ler (pytest toplamaz)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from types import TracebackType
from uuid import UUID, uuid4

from flowpilot.modules.audit.application.dto import AuditRecord
from flowpilot.modules.organization.application.contracts import ActiveMembershipView
from flowpilot.modules.organization.application.invitation_dto import PendingInvitationView
from flowpilot.modules.organization.application.invitation_errors import (
    InvitationConcurrencyError,
)
from flowpilot.modules.organization.application.invitation_ports import (
    InvitationPreviewRow,
    MembershipRecord,
    StoredInvitation,
)
from flowpilot.modules.organization.domain.invitation import Invitation, InvitationStatus
from flowpilot.modules.organization.domain.membership import Membership


class FakeMembershipQuery:
    """(tenant_id, user_id) -> aktif membership rolü eşlemesi."""

    def __init__(self, active: dict[tuple[UUID, UUID], str]) -> None:
        self._active = active

    def find_active(self, *, tenant_id: UUID, user_id: UUID) -> ActiveMembershipView | None:
        role = self._active.get((tenant_id, user_id))
        if role is None:
            return None
        return ActiveMembershipView(
            membership_id=uuid4(), tenant_id=tenant_id, user_id=user_id, role=role
        )

    def find_active_owner(self, *, tenant_id: UUID) -> ActiveMembershipView | None:
        for (tid, uid), role in self._active.items():
            if tid == tenant_id and role == "owner":
                return ActiveMembershipView(
                    membership_id=uuid4(), tenant_id=tid, user_id=uid, role=role
                )
        return None

    def list_active_for_user(self, *, user_id: UUID) -> list[object]:
        return []


class FakeEmailLookup:
    """email (normalize) -> user_id listesi."""

    def __init__(self, mapping: dict[str, list[UUID]] | None = None) -> None:
        self._mapping = mapping or {}

    def find_user_ids_by_email(self, email: str) -> list[UUID]:
        return list(self._mapping.get(email.strip().lower(), []))


class FakeTokenGenerator:
    def __init__(self, tokens: list[str] | None = None) -> None:
        self._tokens = list(tokens) if tokens else ["fake-raw-token"]

    def new_raw_token(self) -> str:
        return self._tokens.pop(0)


class FakeAcceptUrlBuilder:
    def build(self, *, tenant_id: UUID, raw_token: str) -> str:
        return f"/invitations/accept?org={tenant_id}&token={raw_token}"


class FakeAuditWriter:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        self.records.append(record)


class FakeInvitationRepository:
    """In-memory invitation deposu (idempotency + optimistic CAS dahil)."""

    def __init__(self, seed: list[Invitation] | None = None) -> None:
        self.saved: list[Invitation] = list(seed) if seed else []
        self._idempotency: dict[tuple[UUID, str], StoredInvitation] = {}

    def add(
        self,
        invitation: Invitation,
        *,
        idempotency_key: str | None,
        request_fingerprint: str | None,
    ) -> None:
        self.saved.append(invitation)
        if idempotency_key is not None:
            self._idempotency[invitation.tenant_id.value, idempotency_key] = StoredInvitation(
                invitation=invitation, request_fingerprint=request_fingerprint
            )

    def update_checked(self, invitation: Invitation, *, expected_version: int) -> None:
        for index, current in enumerate(self.saved):
            if current.id == invitation.id:
                if current.version != expected_version:
                    raise InvitationConcurrencyError("stale version")
                self.saved[index] = replace(invitation, version=expected_version + 1)
                return
        raise InvitationConcurrencyError("bulunamadı")

    def find_by_id(self, *, tenant_id: UUID, invitation_id: UUID) -> Invitation | None:
        for current in self.saved:
            if current.id.value == invitation_id and current.tenant_id.value == tenant_id:
                return current
        return None

    def find_by_token_hash(self, *, tenant_id: UUID, token_hash: str) -> Invitation | None:
        for current in self.saved:
            if current.tenant_id.value == tenant_id and current.token_hash == token_hash:
                return current
        return None

    def find_pending_by_email(self, *, tenant_id: UUID, invited_email: str) -> Invitation | None:
        # SÜRE FİLTRESİ YOK (gerçek repo ile aynı): süresi geçmiş pending de döner.
        for current in self.saved:
            if (
                current.tenant_id.value == tenant_id
                and current.invited_email == invited_email
                and current.status is InvitationStatus.PENDING
            ):
                return current
        return None

    def find_by_idempotency_key(
        self, *, tenant_id: UUID, idempotency_key: str
    ) -> StoredInvitation | None:
        return self._idempotency.get((tenant_id, idempotency_key))


class FakeInvitationUnitOfWork:
    """Fake repo + fake audit; tek transaction sayaçları."""

    def __init__(self, repository: FakeInvitationRepository, audit: FakeAuditWriter) -> None:
        self.invitations = repository
        self.audit = audit
        self.committed = 0
        self.rolled_back = 0
        self.tenant_context: UUID | None = None
        self.actor_context: UUID | None = None

    def __enter__(self) -> FakeInvitationUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rolled_back += 1

    def set_actor_context(self, actor_user_id: UUID) -> None:
        self.actor_context = actor_user_id

    def set_tenant_context(self, tenant_id: UUID) -> None:
        self.tenant_context = tenant_id

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1


class FakeInvitationQuery:
    def __init__(self, views: list[PendingInvitationView] | None = None) -> None:
        self.views = views or []
        self.calls: list[tuple[UUID, datetime, int]] = []

    def list_pending(
        self, *, tenant_id: UUID, now: datetime, limit: int
    ) -> list[PendingInvitationView]:
        self.calls.append((tenant_id, now, limit))
        return self.views[:limit]


class FakeActorEmailReader:
    def __init__(self, snapshots: dict[UUID, str | None] | None = None) -> None:
        self._snapshots = snapshots or {}

    def find_email_snapshot(self, user_id: object) -> str | None:
        return self._snapshots.get(getattr(user_id, "value", user_id))


class FakeMembershipWriteRepository:
    """In-memory üyelik yazma/okuma (kabul akışı); unique(tenant,user) taklit eder."""

    def __init__(self, seed: dict[tuple[UUID, UUID], MembershipRecord] | None = None) -> None:
        self.records: dict[tuple[UUID, UUID], MembershipRecord] = dict(seed) if seed else {}
        self.added: list[Membership] = []

    def add(self, membership: Membership) -> None:
        key = (membership.tenant_id.value, membership.user_id.value)
        if key in self.records:
            raise RuntimeError("unique(tenant_id,user_id) ihlali (fake)")
        self.records[key] = MembershipRecord(
            membership_id=membership.id.value,
            role=membership.role.value,
            status=membership.status.value,
        )
        self.added.append(membership)

    def find_by_user(self, *, tenant_id: UUID, user_id: UUID) -> MembershipRecord | None:
        return self.records.get((tenant_id, user_id))


class FakeInvitationAcceptUnitOfWork:
    """invitations + memberships + audit; tek transaction sayaçları."""

    def __init__(
        self,
        invitations: FakeInvitationRepository,
        memberships: FakeMembershipWriteRepository,
        audit: FakeAuditWriter,
    ) -> None:
        self.invitations = invitations
        self.memberships = memberships
        self.audit = audit
        self.committed = 0
        self.rolled_back = 0
        self.tenant_context: UUID | None = None
        self.actor_context: UUID | None = None

    def __enter__(self) -> FakeInvitationAcceptUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rolled_back += 1

    def set_actor_context(self, actor_user_id: UUID) -> None:
        self.actor_context = actor_user_id

    def set_tenant_context(self, tenant_id: UUID) -> None:
        self.tenant_context = tenant_id

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1


class FakeInvitationPreviewQuery:
    def __init__(self, rows: dict[tuple[UUID, str], InvitationPreviewRow] | None = None) -> None:
        self._rows = rows or {}

    def find(self, *, tenant_id: UUID, token_hash: str) -> InvitationPreviewRow | None:
        return self._rows.get((tenant_id, token_hash))
