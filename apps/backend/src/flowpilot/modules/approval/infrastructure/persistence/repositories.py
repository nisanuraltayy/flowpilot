"""SQLAlchemy Core tabanlı approval repository'leri + query. COMMIT ETMEZ."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, text
from sqlalchemy.orm import Session

from flowpilot.modules.approval.domain.enums import ApprovalDecisionType
from flowpilot.modules.approval.domain.models import (
    ApprovalComment,
    ApprovalDecision,
    ApprovalDecisionId,
    ApprovalRoleAssignment,
)
from flowpilot.modules.approval.infrastructure.persistence.tables import (
    decisions_table,
    role_assignments_table,
)
from flowpilot.shared.identifiers import TenantId, UserId


def _rowcount(result: object) -> int:
    return int(cast(CursorResult[Any], result).rowcount)


class SqlAlchemyApprovalRoleAssignmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_if_absent(self, assignment: ApprovalRoleAssignment) -> bool:
        # Partial unique (tenant, role_key) WHERE status='active' → tek aktif assignee.
        result = self._session.execute(
            text(
                "INSERT INTO approval_role_assignments "
                "(id, tenant_id, role_key, assigned_user_id, status, created_at, updated_at) "
                "VALUES (:id, :tenant, :role, :user, 'active', :now, :now) "
                "ON CONFLICT (tenant_id, role_key) WHERE status = 'active' DO NOTHING"
            ),
            {
                "id": str(assignment.id.value),
                "tenant": str(assignment.tenant_id.value),
                "role": assignment.role_key.value,
                "user": str(assignment.assigned_user_id.value),
                "now": assignment.created_at,
            },
        )
        self._session.flush()
        return _rowcount(result) == 1


class SqlAlchemyApprovalRoleAssignmentQuery:
    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    def active_map(self, *, tenant_id: UUID) -> dict[str, UUID]:
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :v, true)"),
                {"v": str(tenant_id)},
            )
            rows = session.execute(
                select(
                    role_assignments_table.c.role_key,
                    role_assignments_table.c.assigned_user_id,
                ).where(role_assignments_table.c.status == "active")
            ).all()
        return {str(r[0]): cast(UUID, r[1]) for r in rows}


class SqlAlchemyApprovalDecisionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_if_absent(self, decision: ApprovalDecision) -> bool:
        # Task başına tek terminal karar (unique task_id) + tenant/idempotency_key unique.
        result = self._session.execute(
            text(
                "INSERT INTO approval_decisions "
                "(id, tenant_id, task_id, actor_user_id, decision, comment, idempotency_key, "
                " request_fingerprint, created_at) "
                "VALUES (:id, :tenant, :task, :actor, :decision, :comment, :key, :fp, :now) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "id": str(decision.id.value),
                "tenant": str(decision.tenant_id.value),
                "task": str(decision.task_id),
                "actor": str(decision.actor_user_id.value),
                "decision": decision.decision.value,
                "comment": decision.comment.value,
                "key": decision.idempotency_key,
                "fp": decision.request_fingerprint,
                "now": decision.created_at,
            },
        )
        self._session.flush()
        return _rowcount(result) == 1

    def find_by_task(self, *, task_id: UUID) -> ApprovalDecision | None:
        row = (
            self._session.execute(
                select(decisions_table).where(decisions_table.c.task_id == task_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return ApprovalDecision(
            id=ApprovalDecisionId(row["id"]),
            tenant_id=TenantId(row["tenant_id"]),
            task_id=row["task_id"],
            actor_user_id=UserId(row["actor_user_id"]),
            decision=ApprovalDecisionType(row["decision"]),
            comment=ApprovalComment(row["comment"]),
            idempotency_key=str(row["idempotency_key"]),
            request_fingerprint=str(row["request_fingerprint"]),
            created_at=row["created_at"],
        )
