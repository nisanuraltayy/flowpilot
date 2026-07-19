"""SQLAlchemy tabanlı WorkflowUnitOfWork adapter'ı.

Session (sessionmaker) DIŞARIDAN enjekte edilir; import sırasında engine
oluşturulmaz (ADR-009). RLS transaction context'i `set_config(..., true)` ile
TRANSACTION-LOCAL taşınır — context bir sonraki transaction'a sızmaz. Transaction
sınırı BURADADIR; repository'ler commit etmez (SPK-11 atomikliği bu sınırda tutulur).
"""

from __future__ import annotations

from types import TracebackType
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.workflow_runtime.application.port import (
    DefinitionRepository,
    EventLog,
    InboxStore,
    InstanceRepository,
    OutboxStore,
    TaskRepository,
    TimerStore,
)
from flowpilot.modules.workflow_runtime.infrastructure.persistence.repositories import (
    SqlAlchemyDefinitionRepository,
    SqlAlchemyEventLog,
    SqlAlchemyInboxStore,
    SqlAlchemyInstanceRepository,
    SqlAlchemyOutboxStore,
    SqlAlchemyTaskRepository,
    SqlAlchemyTimerStore,
)


class SqlAlchemyWorkflowUnitOfWork:
    """`WorkflowUnitOfWork` port'unu uygular."""

    definitions: DefinitionRepository
    instances: InstanceRepository
    tasks: TaskRepository
    events: EventLog
    outbox: OutboxStore
    inbox: InboxStore
    timers: TimerStore

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyWorkflowUnitOfWork:
        session = self._session_factory()
        self._session = session
        self.definitions = SqlAlchemyDefinitionRepository(session)
        self.instances = SqlAlchemyInstanceRepository(session)
        self.tasks = SqlAlchemyTaskRepository(session)
        self.events = SqlAlchemyEventLog(session)
        self.outbox = SqlAlchemyOutboxStore(session)
        self.inbox = SqlAlchemyInboxStore(session)
        self.timers = SqlAlchemyTimerStore(session)
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
