"""Composition root wiring — CROSS-MODULE compose adapter'ları YALNIZ burada.

Bu bir wiring dosyasıdır (ADR-009 §2b; import-boundary muafiyeti). İki modülün
infrastructure adapter'larını TEK SQLAlchemy session'ı üzerinde birleştirir; böylece
Purchase Request + workflow instance start AYNI transaction'da commit edilir. İş
mantığı İÇERMEZ — yalnız adapter kompozisyonu.
"""

from __future__ import annotations

from types import TracebackType
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.approval.application.ports import ApprovalDecisionRepository
from flowpilot.modules.approval.infrastructure.persistence.repositories import (
    SqlAlchemyApprovalDecisionRepository,
)
from flowpilot.modules.audit.application.ports import AuditWriterPort
from flowpilot.modules.audit.infrastructure.persistence.writer import SqlAlchemyAuditWriter
from flowpilot.modules.purchase_request.application.dto import InboxItem
from flowpilot.modules.purchase_request.application.ports import PurchaseRequestRepository
from flowpilot.modules.purchase_request.infrastructure.persistence.repository import (
    SqlAlchemyPurchaseRequestRepository,
)
from flowpilot.modules.workflow_runtime.infrastructure.persistence.unit_of_work import (
    SqlAlchemyWorkflowUnitOfWork,
)


class SqlAlchemyPurchaseRequestUnitOfWork(SqlAlchemyWorkflowUnitOfWork):
    """workflow_runtime UoW + purchase_requests repo — TEK session, TEK transaction.

    `SqlAlchemyWorkflowUnitOfWork`'ü genişletir (tüm runtime repo'ları aynı session'da
    kurulur) ve purchase_requests repo'sunu EKLER. Böylece iki modülün yazımları tek
    commit/rollback ile atomiktir ve tek tenant context altındadır.
    """

    purchase_requests: PurchaseRequestRepository
    audit: AuditWriterPort

    def __enter__(self) -> SqlAlchemyPurchaseRequestUnitOfWork:
        super().__enter__()
        session = self._require_session()
        self.purchase_requests = SqlAlchemyPurchaseRequestRepository(session)
        self.audit = SqlAlchemyAuditWriter(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        super().__exit__(exc_type, exc, tb)


def purchase_request_uow_factory(
    session_factory: sessionmaker[Session],
) -> SqlAlchemyPurchaseRequestUnitOfWork:
    return SqlAlchemyPurchaseRequestUnitOfWork(session_factory)


class SqlAlchemyApprovalDecisionUnitOfWork(SqlAlchemyPurchaseRequestUnitOfWork):
    """runtime UoW + purchase_requests + approval_decisions + audit — TEK transaction.

    Onay kararı akışının cross-module ATOMİKLİĞİNİ sağlar: runtime task transition +
    PR status + ApprovalDecision + audit AYNI session/transaction'da commit edilir.
    """

    approval_decisions: ApprovalDecisionRepository
    # `audit` parent'ta (SqlAlchemyPurchaseRequestUnitOfWork) zaten kurulur — miras alınır.

    def __enter__(self) -> SqlAlchemyApprovalDecisionUnitOfWork:
        super().__enter__()
        session = self._require_session()
        self.approval_decisions = SqlAlchemyApprovalDecisionRepository(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        super().__exit__(exc_type, exc, tb)


class SqlAlchemyTaskInboxReadModel:
    """`TaskInboxQuery` — actor'a atanmış AKTİF task'ları PR verisiyle birleştiren read model.

    Cross-module JOIN (workflow_runtime_tasks + purchase_request_requests) yalnız
    composition root'ta (wiring dosyası) yapılır. RLS tenant-scoped; başka kullanıcının
    task'ı görünmez (assigned_user_id filtresi + policy).
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_pending_for_user(
        self, *, tenant_id: UUID, user_id: UUID, limit: int
    ) -> list[InboxItem]:
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :v, true)"),
                {"v": str(tenant_id)},
            )
            rows = (
                session.execute(
                    text(
                        "SELECT t.id AS task_id, t.instance_id, t.approver_role, t.status, "
                        "t.created_at, p.id AS pr_id, p.title, p.amount_minor, p.currency "
                        "FROM workflow_runtime_tasks t "
                        "JOIN purchase_request_requests p "
                        "  ON p.workflow_instance_id = t.instance_id "
                        "WHERE t.assigned_user_id = :user AND t.status = 'active' "
                        "ORDER BY t.created_at DESC, t.id DESC LIMIT :limit"
                    ),
                    {"user": str(user_id), "limit": limit},
                )
                .mappings()
                .all()
            )
        return [
            InboxItem(
                task_id=row["task_id"],
                purchase_request_id=row["pr_id"],
                purchase_request_title=str(row["title"]),
                amount_minor=int(row["amount_minor"]),
                currency=str(row["currency"]),
                required_role=str(row["approver_role"]),
                status=str(row["status"]),
                workflow_instance_id=row["instance_id"],
                created_at=row["created_at"],
                due_at=None,
            )
            for row in rows
        ]
