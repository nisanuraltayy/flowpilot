"""SQLAlchemy Core `InvitationRepository` adapter'ı.

Domain ↔ satır eşlemesi burada; domain SQLAlchemy bilmez. `add`/`update_checked`
`flush()` eder ki RLS/constraint erken değerlendirilsin. Ham token BU KATMANA
GELMEZ — yalnız `token_hash` yazılır.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, Row, insert, select, update
from sqlalchemy.orm import Session

from flowpilot.modules.organization.application.invitation_errors import (
    InvitationConcurrencyError,
)
from flowpilot.modules.organization.application.invitation_ports import StoredInvitation
from flowpilot.modules.organization.domain.invitation import (
    Invitation,
    InvitationStatus,
)
from flowpilot.modules.organization.domain.membership import MembershipRole
from flowpilot.modules.organization.infrastructure.persistence.tables import invitations_table
from flowpilot.shared.identifiers import InvitationId, TenantId, UserId


def _row_to_invitation(row: Row[Any]) -> Invitation:
    return Invitation(
        id=InvitationId(row.id),
        tenant_id=TenantId(row.tenant_id),
        invited_email=row.invited_email,
        role=MembershipRole(row.role),
        status=InvitationStatus(row.status),
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        invited_by_user_id=UserId(row.invited_by_user_id),
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
        accepted_by_user_id=UserId(row.accepted_by_user_id) if row.accepted_by_user_id else None,
        accepted_at=row.accepted_at,
    )


class SqlAlchemyInvitationRepository:
    """`InvitationRepository` port'unu uygular."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        invitation: Invitation,
        *,
        idempotency_key: str | None,
        request_fingerprint: str | None,
    ) -> None:
        self._session.execute(
            insert(invitations_table).values(
                id=invitation.id.value,
                tenant_id=invitation.tenant_id.value,
                invited_email=invitation.invited_email,
                role=invitation.role.value,
                token_hash=invitation.token_hash,
                status=invitation.status.value,
                expires_at=invitation.expires_at,
                invited_by_user_id=invitation.invited_by_user_id.value,
                accepted_by_user_id=None,
                accepted_at=None,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                version=invitation.version,
                created_at=invitation.created_at,
                updated_at=invitation.updated_at,
            )
        )
        self._session.flush()

    def update_checked(self, invitation: Invitation, *, expected_version: int) -> None:
        # Optimistic CAS: yalnız beklenen version eşleşirse günceller; version + 1.
        result = self._session.execute(
            update(invitations_table)
            .where(
                invitations_table.c.id == invitation.id.value,
                invitations_table.c.tenant_id == invitation.tenant_id.value,
                invitations_table.c.version == expected_version,
            )
            .values(
                status=invitation.status.value,
                accepted_by_user_id=(
                    invitation.accepted_by_user_id.value if invitation.accepted_by_user_id else None
                ),
                accepted_at=invitation.accepted_at,
                updated_at=invitation.updated_at,
                version=expected_version + 1,
            )
        )
        if int(cast(CursorResult[Any], result).rowcount) != 1:
            raise InvitationConcurrencyError("davet güncelleme çakışması (stale version)")
        self._session.flush()

    def find_by_id(self, *, tenant_id: UUID, invitation_id: UUID) -> Invitation | None:
        row = self._session.execute(
            select(invitations_table).where(
                invitations_table.c.id == invitation_id,
                invitations_table.c.tenant_id == tenant_id,
            )
        ).first()
        return _row_to_invitation(row) if row is not None else None

    def find_by_token_hash(self, *, tenant_id: UUID, token_hash: str) -> Invitation | None:
        # Tenant-scoped token lookup (unique (tenant_id, token_hash)). RLS ek savunma:
        # yanlış tenant context'inde satır görünmez → cross-tenant token reddedilir.
        row = self._session.execute(
            select(invitations_table).where(
                invitations_table.c.tenant_id == tenant_id,
                invitations_table.c.token_hash == token_hash,
            )
        ).first()
        return _row_to_invitation(row) if row is not None else None

    def find_pending_by_email(self, *, tenant_id: UUID, invited_email: str) -> Invitation | None:
        # SÜRE FİLTRESİ YOK: süresi geçmiş pending de döner (expiry use-case'te belirlenir).
        # Partial unique (status='pending') gereği en fazla bir satır olur.
        row = self._session.execute(
            select(invitations_table).where(
                invitations_table.c.tenant_id == tenant_id,
                invitations_table.c.invited_email == invited_email,
                invitations_table.c.status == InvitationStatus.PENDING.value,
            )
        ).first()
        return _row_to_invitation(row) if row is not None else None

    def find_by_idempotency_key(
        self, *, tenant_id: UUID, idempotency_key: str
    ) -> StoredInvitation | None:
        row = self._session.execute(
            select(invitations_table).where(
                invitations_table.c.tenant_id == tenant_id,
                invitations_table.c.idempotency_key == idempotency_key,
            )
        ).first()
        if row is None:
            return None
        return StoredInvitation(
            invitation=_row_to_invitation(row),
            request_fingerprint=row.request_fingerprint,
        )
