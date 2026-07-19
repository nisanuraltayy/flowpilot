"""Standalone approval assignment UnitOfWork (EnsureDefault provisioning için).

Compose UoW (decision akışı) composition root'tadır; bu, YALNIZ assignment
provisioning'in kendi transaction'ıdır. RLS context transaction-local.
"""

from __future__ import annotations

from types import TracebackType
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.approval.application.ports import ApprovalRoleAssignmentRepository
from flowpilot.modules.approval.infrastructure.persistence.repositories import (
    SqlAlchemyApprovalRoleAssignmentRepository,
)


class SqlAlchemyApprovalAssignmentUnitOfWork:
    """`ApprovalAssignmentUnitOfWork` port'unu uygular."""

    # Port tipiyle annotate (invariant Protocol attribute uyumu için).
    approval_role_assignments: ApprovalRoleAssignmentRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyApprovalAssignmentUnitOfWork:
        session = self._session_factory()
        self._session = session
        self.approval_role_assignments = SqlAlchemyApprovalRoleAssignmentRepository(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exc_type is not None:
                session.rollback()
        finally:
            session.close()
            self._session = None

    def set_actor_context(self, actor_user_id: UUID) -> None:
        self._require_session().execute(
            text("SELECT set_config('app.current_actor_id', :value, true)"),
            {"value": str(actor_user_id)},
        )

    def set_tenant_context(self, tenant_id: UUID) -> None:
        self._require_session().execute(
            text("SELECT set_config('app.current_tenant_id', :value, true)"),
            {"value": str(tenant_id)},
        )

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork aktif değil — 'with uow:' bloğu içinde kullanın.")
        return self._session
