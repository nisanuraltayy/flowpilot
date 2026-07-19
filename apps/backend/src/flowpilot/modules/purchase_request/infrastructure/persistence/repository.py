"""SQLAlchemy Core tabanlı PurchaseRequestRepository adapter'ı.

Domain ↔ satır eşlemesi burada; domain SQLAlchemy bilmez. COMMIT ETMEZ —
transaction sınırı compose UnitOfWork'tedir. update_checked optimistic version CAS
yapar; stale write kontrollü PurchaseRequestConcurrencyError üretir.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, and_, insert, select, update
from sqlalchemy.orm import Session

from flowpilot.modules.purchase_request.domain.errors import PurchaseRequestConcurrencyError
from flowpilot.modules.purchase_request.domain.identifiers import PurchaseRequestId
from flowpilot.modules.purchase_request.domain.money import Money
from flowpilot.modules.purchase_request.domain.purchase_request import (
    PurchaseRequest,
    PurchaseRequestStatus,
)
from flowpilot.modules.purchase_request.domain.value_objects import (
    PurchaseRequestDescription,
    PurchaseRequestTitle,
)
from flowpilot.modules.purchase_request.infrastructure.persistence.tables import requests_table
from flowpilot.shared.identifiers import TenantId, UserId


class SqlAlchemyPurchaseRequestRepository:
    """`PurchaseRequestRepository` port'unu uygular."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, request: PurchaseRequest) -> None:
        self._session.execute(
            insert(requests_table).values(
                id=request.id.value,
                tenant_id=request.tenant_id.value,
                requested_by_user_id=request.requested_by.value,
                title=request.title.value,
                description=request.description.value,
                amount_minor=request.money.amount_minor,
                currency=request.money.currency,
                status=request.status.value,
                workflow_instance_id=request.workflow_instance_id,
                version=request.version,
                created_at=request.created_at,
                updated_at=request.updated_at,
            )
        )
        self._session.flush()

    def update_checked(self, request: PurchaseRequest, *, expected_version: int) -> None:
        result = self._session.execute(
            update(requests_table)
            .where(
                and_(
                    requests_table.c.id == request.id.value,
                    requests_table.c.version == expected_version,
                )
            )
            .values(
                title=request.title.value,
                description=request.description.value,
                amount_minor=request.money.amount_minor,
                currency=request.money.currency,
                status=request.status.value,
                workflow_instance_id=request.workflow_instance_id,
                version=request.version,
                updated_at=request.updated_at,
            )
        )
        if int(cast(CursorResult[Any], result).rowcount) != 1:
            raise PurchaseRequestConcurrencyError(
                "purchase request eşzamanlı değişti — 409 (sessiz overwrite yok)"
            )

    def get_by_workflow_instance(self, workflow_instance_id: UUID) -> PurchaseRequest | None:
        row = (
            self._session.execute(
                select(requests_table).where(
                    requests_table.c.workflow_instance_id == workflow_instance_id
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return PurchaseRequest(
            id=PurchaseRequestId(row["id"]),
            tenant_id=TenantId(row["tenant_id"]),
            requested_by=UserId(row["requested_by_user_id"]),
            title=PurchaseRequestTitle(str(row["title"])),
            description=PurchaseRequestDescription(row["description"]),
            money=Money(amount_minor=int(row["amount_minor"]), currency=str(row["currency"])),
            status=PurchaseRequestStatus(row["status"]),
            workflow_instance_id=row["workflow_instance_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=int(row["version"]),
        )
