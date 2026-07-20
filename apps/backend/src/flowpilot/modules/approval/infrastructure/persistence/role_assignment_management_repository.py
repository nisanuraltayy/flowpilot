"""Session-tabanlı `ApprovalRoleAssignmentManagementRepository` adapter'ı (reassign).

Rol atama güncelleme transaction'ının parçası olarak AYNI session üzerinde çalışır.
Tenant+role advisory xact lock ile eşzamanlı aynı-rol atamalarını serileştirir; aktif
atamayı `FOR UPDATE` ile kilitler; optimistic `version` CAS ile revoke eder ve yeni aktif
satır ekler. Fiziksel DELETE yapmaz (soft-remove: eski satır `revoked` olarak kalır).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from flowpilot.modules.approval.application.role_assignment_errors import (
    ApprovalRoleAssignmentConcurrencyError,
)
from flowpilot.modules.approval.domain.enums import ApprovalRoleKey
from flowpilot.modules.approval.domain.models import (
    ApprovalAssignmentStatus,
    ApprovalRoleAssignment,
    ApprovalRoleAssignmentId,
)
from flowpilot.modules.approval.infrastructure.persistence.tables import role_assignments_table
from flowpilot.shared.identifiers import TenantId, UserId


class SqlAlchemyApprovalRoleAssignmentManagementRepository:
    """`ApprovalRoleAssignmentManagementRepository` port'unu uygular."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def acquire_role_lock(self, *, tenant_id: UUID, role_key: ApprovalRoleKey) -> None:
        # Transaction advisory lock: (tenant, role_key) başına atamaları serileştirir →
        # eşzamanlı iki farklı-user atamasında yalnız biri kazanır (deadlock-safe sıralama).
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"approval_role_assignment:{tenant_id}:{role_key.value}"},
        )

    def find_active_for_update(
        self, *, tenant_id: UUID, role_key: ApprovalRoleKey
    ) -> ApprovalRoleAssignment | None:
        row = self._session.execute(
            select(role_assignments_table)
            .where(
                role_assignments_table.c.tenant_id == tenant_id,
                role_assignments_table.c.role_key == role_key.value,
                role_assignments_table.c.status == ApprovalAssignmentStatus.ACTIVE.value,
            )
            .with_for_update()
        ).first()
        if row is None:
            return None
        return ApprovalRoleAssignment(
            id=ApprovalRoleAssignmentId(row.id),
            tenant_id=TenantId(row.tenant_id),
            role_key=ApprovalRoleKey(row.role_key),
            assigned_user_id=UserId(row.assigned_user_id),
            status=ApprovalAssignmentStatus(row.status),
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def revoke_checked(
        self, assignment: ApprovalRoleAssignment, *, expected_version: int, now: datetime
    ) -> None:
        result = self._session.execute(
            update(role_assignments_table)
            .where(
                role_assignments_table.c.id == assignment.id.value,
                role_assignments_table.c.tenant_id == assignment.tenant_id.value,
                role_assignments_table.c.version == expected_version,
                role_assignments_table.c.status == ApprovalAssignmentStatus.ACTIVE.value,
            )
            .values(
                status=ApprovalAssignmentStatus.REVOKED.value,
                version=expected_version + 1,
                updated_at=now,
            )
        )
        if int(cast(CursorResult[Any], result).rowcount) != 1:
            raise ApprovalRoleAssignmentConcurrencyError("atama eşzamanlı değişti (stale version)")
        self._session.flush()

    def insert_active(self, assignment: ApprovalRoleAssignment) -> None:
        try:
            self._session.execute(
                role_assignments_table.insert().values(
                    id=assignment.id.value,
                    tenant_id=assignment.tenant_id.value,
                    role_key=assignment.role_key.value,
                    assigned_user_id=assignment.assigned_user_id.value,
                    status=ApprovalAssignmentStatus.ACTIVE.value,
                    version=assignment.version,
                    created_at=assignment.created_at,
                    updated_at=assignment.updated_at,
                )
            )
            self._session.flush()
        except IntegrityError as exc:
            # Partial unique (tenant, role_key WHERE active) — advisory lock'a rağmen yarış
            # olursa güvenli conflict'e dönüştür (çift aktif atama oluşmaz).
            raise ApprovalRoleAssignmentConcurrencyError(
                "aktif atama zaten var (eşzamanlı atama)"
            ) from exc
