"""`PurchaseRequestReadQuery` adapter'ı — RLS-scoped tek talep okuması.

Kendi kısa-ömürlü session'ını açar, tenant context set eder ve YALNIZ current tenant
scope'undaki talebi döndürür (cross-tenant IDOR RLS ile engellenir). Workflow durumu
ve current approval role BU adapter'da doldurulmaz; GET use-case runtime port'undan
zenginleştirir.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.purchase_request.application.dto import (
    PurchaseRequestDetail,
    PurchaseRequestListItem,
)
from flowpilot.modules.purchase_request.infrastructure.persistence.tables import requests_table


class SqlAlchemyPurchaseRequestReadQuery:
    """`PurchaseRequestReadQuery` port'unu uygular."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(
        self, *, tenant_id: UUID, purchase_request_id: UUID, current_user_id: UUID
    ) -> PurchaseRequestDetail | None:
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :v, true)"),
                {"v": str(tenant_id)},
            )
            row = (
                session.execute(
                    select(requests_table).where(requests_table.c.id == purchase_request_id)
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return PurchaseRequestDetail(
            purchase_request_id=row["id"],
            tenant_id=row["tenant_id"],
            requested_by_current_user=row["requested_by_user_id"] == current_user_id,
            title=str(row["title"]),
            description=row["description"],
            amount_minor=int(row["amount_minor"]),
            currency=str(row["currency"]),
            status=str(row["status"]),
            workflow_instance_id=row["workflow_instance_id"],
            workflow_status=None,
            current_approval_role=None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_for_requester(
        self, *, tenant_id: UUID, requester_user_id: UUID, limit: int
    ) -> list[PurchaseRequestListItem]:
        with self._session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :v, true)"),
                {"v": str(tenant_id)},
            )
            rows = (
                session.execute(
                    select(requests_table)
                    .where(requests_table.c.requested_by_user_id == requester_user_id)
                    .order_by(requests_table.c.created_at.desc(), requests_table.c.id.desc())
                    .limit(limit)
                )
                .mappings()
                .all()
            )
        return [
            PurchaseRequestListItem(
                purchase_request_id=row["id"],
                title=str(row["title"]),
                amount_minor=int(row["amount_minor"]),
                currency=str(row["currency"]),
                status=str(row["status"]),
                current_approval_role=None,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
