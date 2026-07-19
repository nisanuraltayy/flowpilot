"""Purchase Request integration testleri için ortak yardımcılar (pytest toplamaz).

Handler'ı gerçek flowpilot_app sessionmaker'ı + composed UoW ile kurar; membership
fixture'larını gerçek organization tablolarına yazar (RLS'e tabi).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.api.wiring import SqlAlchemyPurchaseRequestUnitOfWork
from flowpilot.modules.organization.infrastructure.persistence.membership_query import (
    SqlAlchemyMembershipQuery,
)
from flowpilot.modules.purchase_request.application.create_handler import (
    CreatePurchaseRequestHandler,
)
from flowpilot.modules.purchase_request.application.get_handler import GetPurchaseRequestHandler
from flowpilot.modules.purchase_request.infrastructure.persistence.read_query import (
    SqlAlchemyPurchaseRequestReadQuery,
)
from flowpilot.modules.workflow_runtime.application.service import WorkflowRuntimeService
from flowpilot.modules.workflow_runtime.infrastructure.persistence.unit_of_work import (
    SqlAlchemyWorkflowUnitOfWork,
)
from flowpilot.shared.clock import SystemClock
from flowpilot.shared.ids import UuidGenerator

AMOUNT_UNDER_10K = 999_999
AMOUNT_10K = 1_000_000
AMOUNT_50K = 5_000_000
AMOUNT_OVER_50K = 5_000_001


def build_runtime(app_sessionmaker: sessionmaker[Session]) -> WorkflowRuntimeService:
    return WorkflowRuntimeService(
        unit_of_work_factory=lambda: SqlAlchemyWorkflowUnitOfWork(app_sessionmaker),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def build_create_handler(
    app_sessionmaker: sessionmaker[Session],
) -> CreatePurchaseRequestHandler:
    runtime = build_runtime(app_sessionmaker)
    return CreatePurchaseRequestHandler(
        unit_of_work_factory=lambda: SqlAlchemyPurchaseRequestUnitOfWork(app_sessionmaker),
        membership_query=SqlAlchemyMembershipQuery(app_sessionmaker),
        provisioning=runtime,
        runtime=runtime,
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def build_get_handler(app_sessionmaker: sessionmaker[Session]) -> GetPurchaseRequestHandler:
    return GetPurchaseRequestHandler(
        read_query=SqlAlchemyPurchaseRequestReadQuery(app_sessionmaker),
        runtime=build_runtime(app_sessionmaker),
    )


def seed_tenant_with_member(
    app_sessionmaker: sessionmaker[Session],
    *,
    role: str = "owner",
    status: str = "active",
) -> tuple[UUID, UUID]:
    """Bir identity user + tenant + membership yaratır; (tenant_id, user_id) döndürür.

    RLS: tenant INSERT actor context ister; membership INSERT tenant context ister
    (0001 policy'leri). Bu yardımcı gerçek policy yollarını kullanır.
    """
    tenant_id = uuid4()
    user_id = uuid4()
    with app_sessionmaker() as s, s.begin():
        # identity_users GLOBAL (RLS yok).
        s.execute(
            text(
                "INSERT INTO identity_users (id, email_snapshot, auth_provider, "
                "provider_subject, created_at) VALUES (:id, :email, 'supabase', :sub, now())"
            ),
            {"id": str(user_id), "email": "u@example.test", "sub": str(user_id)},
        )
    with app_sessionmaker() as s, s.begin():
        s.execute(text("SELECT set_config('app.current_actor_id', :a, true)"), {"a": str(user_id)})
        s.execute(
            text(
                "INSERT INTO organization_tenants (id, name, status, created_by_user_id, "
                "created_at) VALUES (:id, :name, 'active', :actor, now())"
            ),
            {"id": str(tenant_id), "name": "Test Org", "actor": str(user_id)},
        )
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        s.execute(
            text(
                "INSERT INTO organization_memberships (id, tenant_id, user_id, role, status, "
                "created_at) VALUES (:id, :tenant, :user, :role, :status, now())"
            ),
            {
                "id": str(uuid4()),
                "tenant": str(tenant_id),
                "user": str(user_id),
                "role": role,
                "status": status,
            },
        )
    return tenant_id, user_id


def scoped_count(
    app_sessionmaker: sessionmaker[Session], tenant_id: UUID, table: str, **where: str
) -> int:
    clause = " AND ".join(f"{k} = :{k}" for k in where) or "TRUE"
    with app_sessionmaker() as s, s.begin():
        s.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"), {"v": str(tenant_id)}
        )
        value = s.execute(
            text(f"SELECT count(*) FROM {table} WHERE {clause}"),  # noqa: S608 — test yardımcı
            dict(where.items()),
        ).scalar_one()
    return int(value)
