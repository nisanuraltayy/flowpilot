"""Worker composition root — adapter wiring (YALNIZ burada, ADR-009 §2b).

Bu dosya iş mantığı İÇERMEZ; yalnız application sınırlarını (WorkflowRuntimeService)
somut infrastructure adapter'larıyla (SQLAlchemy UnitOfWork) bağlar. Engine import
sırasında oluşturulmaz; `build_runtime()` çağrıldığında oluşturulur.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.config.settings import Settings
from flowpilot.modules.workflow_runtime.application.service import WorkflowRuntimeService
from flowpilot.modules.workflow_runtime.infrastructure.persistence.unit_of_work import (
    SqlAlchemyWorkflowUnitOfWork,
)
from flowpilot.shared.clock import SystemClock
from flowpilot.shared.ids import UuidGenerator


@dataclass
class RuntimeWiring:
    """Wire edilmiş runtime servis + arkasındaki engine (dispose için)."""

    service: WorkflowRuntimeService
    engine: Engine

    def dispose(self) -> None:
        self.engine.dispose()


def build_runtime(settings: Settings) -> RuntimeWiring:
    """Application rolü (flowpilot_app, NOBYPASSRLS) ile runtime servisi kurar."""
    engine = create_engine(settings.require_database_url())
    session_factory: sessionmaker[Session] = sessionmaker(bind=engine)
    service = WorkflowRuntimeService(
        unit_of_work_factory=lambda: SqlAlchemyWorkflowUnitOfWork(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )
    return RuntimeWiring(service=service, engine=engine)
