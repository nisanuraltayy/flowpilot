"""Approval rol atama integration testleri için ortak yardımcılar (pytest toplamaz)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.approval.application.role_assignment_handlers import (
    AssignApprovalRoleHandler,
    ListApprovalRoleAssignmentsHandler,
)
from flowpilot.modules.organization.infrastructure.persistence.membership_query import (
    SqlAlchemyMembershipQuery,
)
from flowpilot.shared.clock import SystemClock
from flowpilot.shared.ids import UuidGenerator


def build_assign_approval_role_handler(
    app_sessionmaker: sessionmaker[Session],
) -> AssignApprovalRoleHandler:
    # deps.py wiring'ini yansıtır (SqlAlchemyApprovalRoleAssignmentUpdateUnitOfWork).
    from flowpilot.api.wiring import SqlAlchemyApprovalRoleAssignmentUpdateUnitOfWork

    return AssignApprovalRoleHandler(
        unit_of_work_factory=lambda: SqlAlchemyApprovalRoleAssignmentUpdateUnitOfWork(
            app_sessionmaker
        ),
        membership_query=SqlAlchemyMembershipQuery(app_sessionmaker),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def build_list_approval_roles_handler(
    app_sessionmaker: sessionmaker[Session],
) -> ListApprovalRoleAssignmentsHandler:
    from flowpilot.api.wiring import SqlAlchemyApprovalRoleAssignmentListReadModel

    return ListApprovalRoleAssignmentsHandler(
        list_query=SqlAlchemyApprovalRoleAssignmentListReadModel(app_sessionmaker),
        membership_query=SqlAlchemyMembershipQuery(app_sessionmaker),
    )


def assignment_rows(
    app_sessionmaker: sessionmaker[Session], *, tenant_id: UUID
) -> list[dict[str, object]]:
    """Tenant scope'undaki TÜM (active+revoked) atama satırları — DB doğrulaması için."""
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        rows = (
            s.execute(
                text(
                    "SELECT id, role_key, assigned_user_id, status, version "
                    "FROM approval_role_assignments WHERE tenant_id = :t "
                    "ORDER BY role_key, version"
                ),
                {"t": str(tenant_id)},
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]


def active_assignment(
    app_sessionmaker: sessionmaker[Session], *, tenant_id: UUID, role_key: str
) -> dict[str, object] | None:
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        row = (
            s.execute(
                text(
                    "SELECT id, assigned_user_id, status, version "
                    "FROM approval_role_assignments "
                    "WHERE tenant_id = :t AND role_key = :r AND status = 'active'"
                ),
                {"t": str(tenant_id), "r": role_key},
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def task_assignee(
    app_sessionmaker: sessionmaker[Session], *, tenant_id: UUID, instance_id: UUID, role: str
) -> UUID | None:
    """Bir workflow instance'ında verilen approver_role step'inin pinlenmiş assignee'si."""
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        row = s.execute(
            text(
                "SELECT assigned_user_id FROM workflow_runtime_tasks "
                "WHERE instance_id = :i AND approver_role = :r"
            ),
            {"i": str(instance_id), "r": role},
        ).first()
    if row is None or row[0] is None:
        return None
    return UUID(str(row[0]))
