"""Session-tabanlı `MembershipManagementRepository` adapter'ı (üye yönetimi).

Üye güncelleme transaction'ının parçası olarak AYNI session üzerinde çalışır. Hedef
üyeliği ve aktif owner satırlarını `FOR UPDATE` ile kilitler (final-owner yarış güvenliği),
optimistic `version` CAS ile günceller. Fiziksel DELETE yapmaz (soft-remove status ile).
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, Row, select, text, update
from sqlalchemy.orm import Session

from flowpilot.modules.organization.application.member_errors import MembershipConcurrencyError
from flowpilot.modules.organization.domain.membership import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from flowpilot.modules.organization.infrastructure.persistence.tables import memberships_table
from flowpilot.shared.identifiers import MembershipId, TenantId, UserId


def _row_to_membership(row: Row[Any]) -> Membership:
    return Membership(
        id=MembershipId(row.id),
        tenant_id=TenantId(row.tenant_id),
        user_id=UserId(row.user_id),
        role=MembershipRole(row.role),
        status=MembershipStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        version=row.version,
    )


class SqlAlchemyMembershipManagementRepository:
    """`MembershipManagementRepository` port'unu uygular."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def acquire_tenant_lock(self, *, tenant_id: UUID) -> None:
        # Transaction advisory lock: tenant başına üye güncellemelerini serileştirir.
        # hashtext(tenant) deterministik bir int64 key üretir; xact scope commit/rollback'te
        # otomatik serbest bırakılır. Owner-invariant yarışında tutarlı kilit sırası verir.
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"organization_membership:{tenant_id}"},
        )

    def find_by_user_for_update(self, *, tenant_id: UUID, user_id: UUID) -> Membership | None:
        row = self._session.execute(
            select(memberships_table)
            .where(
                memberships_table.c.tenant_id == tenant_id,
                memberships_table.c.user_id == user_id,
            )
            .with_for_update()
        ).first()
        if row is None:
            return None
        return _row_to_membership(row)

    def count_active_owners_for_update(self, *, tenant_id: UUID) -> int:
        # Aktif owner satırlarını KİLİTLE (FOR UPDATE), sonra say. İki eşzamanlı owner-deaktive
        # işlemini serileştirir → sıfır owner bırakmaz. (Satırları kilitleyip ayrıca sayarız;
        # count(*) tek başına FOR UPDATE alamaz.)
        locked = self._session.execute(
            select(memberships_table.c.id)
            .where(
                memberships_table.c.tenant_id == tenant_id,
                memberships_table.c.role == MembershipRole.OWNER.value,
                memberships_table.c.status == MembershipStatus.ACTIVE.value,
            )
            .with_for_update()
        ).all()
        return len(locked)

    def update_checked(self, membership: Membership, *, expected_version: int) -> None:
        result = self._session.execute(
            update(memberships_table)
            .where(
                memberships_table.c.id == membership.id.value,
                memberships_table.c.tenant_id == membership.tenant_id.value,
                memberships_table.c.version == expected_version,
            )
            .values(
                role=membership.role.value,
                status=membership.status.value,
                updated_at=membership.updated_at,
                version=expected_version + 1,
            )
        )
        if int(cast(CursorResult[Any], result).rowcount) != 1:
            raise MembershipConcurrencyError("üyelik eşzamanlı değişti (stale version)")
        self._session.flush()
