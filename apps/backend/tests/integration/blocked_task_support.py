"""Blocked approval task (self-approval) integration testleri için yardımcılar (toplanmaz)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.approval.application.blocked_task_handlers import (
    ListBlockedApprovalTasksHandler,
    ResolveBlockedApprovalTaskHandler,
)
from flowpilot.modules.organization.infrastructure.persistence.membership_query import (
    SqlAlchemyMembershipQuery,
)
from flowpilot.shared.clock import SystemClock
from flowpilot.shared.ids import UuidGenerator
from tests.integration.purchase_support import build_runtime


def build_resolve_blocked_task_handler(
    app_sessionmaker: sessionmaker[Session],
) -> ResolveBlockedApprovalTaskHandler:
    from flowpilot.api.wiring import SqlAlchemyResolveBlockedTaskUnitOfWork

    return ResolveBlockedApprovalTaskHandler(
        unit_of_work_factory=lambda: SqlAlchemyResolveBlockedTaskUnitOfWork(app_sessionmaker),
        membership_query=SqlAlchemyMembershipQuery(app_sessionmaker),
        runtime=build_runtime(app_sessionmaker),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def build_list_blocked_tasks_handler(
    app_sessionmaker: sessionmaker[Session],
) -> ListBlockedApprovalTasksHandler:
    from flowpilot.api.wiring import SqlAlchemyBlockedApprovalTaskListReadModel

    return ListBlockedApprovalTasksHandler(
        list_query=SqlAlchemyBlockedApprovalTaskListReadModel(app_sessionmaker),
        membership_query=SqlAlchemyMembershipQuery(app_sessionmaker),
    )


def task_row(
    app_sessionmaker: sessionmaker[Session], *, tenant_id: UUID, instance_id: UUID, role: str
) -> dict[str, object] | None:
    """Bir instance'ın verilen approver_role step'inin (status/assignee/reason) satırı."""
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        row = (
            s.execute(
                text(
                    "SELECT id, status, assigned_user_id, blocked_reason, version "
                    "FROM workflow_runtime_tasks "
                    "WHERE instance_id = :i AND approver_role = :r"
                ),
                {"i": str(instance_id), "r": role},
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None
