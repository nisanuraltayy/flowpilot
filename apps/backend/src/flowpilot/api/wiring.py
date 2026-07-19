"""Composition root wiring — CROSS-MODULE compose adapter'ları YALNIZ burada.

Bu bir wiring dosyasıdır (ADR-009 §2b; import-boundary muafiyeti). İki modülün
infrastructure adapter'larını TEK SQLAlchemy session'ı üzerinde birleştirir; böylece
Purchase Request + workflow instance start AYNI transaction'da commit edilir. İş
mantığı İÇERMEZ — yalnız adapter kompozisyonu.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

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

    def __enter__(self) -> SqlAlchemyPurchaseRequestUnitOfWork:
        super().__enter__()
        self.purchase_requests = SqlAlchemyPurchaseRequestRepository(self._require_session())
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
