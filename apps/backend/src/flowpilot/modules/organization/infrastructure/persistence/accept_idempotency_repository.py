"""Session-tabanlı `AcceptIdempotencyRepository` adapter'ı (davet kabul idempotency'si).

Kabul transaction'ının parçası olarak AYNI session üzerinde çalışır. `find_for_actor`
actor-scoped RLS ile kullanıcının KENDİ kaydını (cross-tenant) okur; `add_if_absent`
ON CONFLICT DO NOTHING ile unique(tenant,actor,key) yarışında tek kazanan sağlar.
Ham token/token_hash saklanmaz — yalnız request_fingerprint (hash).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from flowpilot.modules.organization.application.invitation_ports import AcceptIdempotencyRecord
from flowpilot.modules.organization.infrastructure.persistence.tables import (
    invitation_accept_idempotency_table,
)


class SqlAlchemyAcceptIdempotencyRepository:
    """`AcceptIdempotencyRepository` port'unu uygular."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_for_actor(
        self, *, actor_user_id: UUID, idempotency_key: str
    ) -> AcceptIdempotencyRecord | None:
        # Actor-scoped RLS: kullanıcı KENDİ kaydını cross-tenant görür. "Aynı key farklı
        # org → 409" için gerekir. En fazla bir kayıt (cross-org ikinci kullanım 409'lanır).
        row = self._session.execute(
            select(invitation_accept_idempotency_table).where(
                invitation_accept_idempotency_table.c.actor_user_id == actor_user_id,
                invitation_accept_idempotency_table.c.idempotency_key == idempotency_key,
            )
        ).first()
        if row is None:
            return None
        return AcceptIdempotencyRecord(
            tenant_id=row.tenant_id,
            actor_user_id=row.actor_user_id,
            idempotency_key=row.idempotency_key,
            request_fingerprint=row.request_fingerprint,
            invitation_id=row.invitation_id,
            membership_id=row.membership_id,
            response_role=row.response_role,
            response_status=row.response_status,
            response_duplicate=row.response_duplicate,
        )

    def add_if_absent(
        self, record: AcceptIdempotencyRecord, *, record_id: UUID, now: datetime
    ) -> bool:
        # RETURNING ile eklenip eklenmediğini GÜVENİLİR biçimde tespit et: ON CONFLICT DO
        # NOTHING'de rowcount sürücüye göre güvenilmezdir; eklendiyse RETURNING satır döner,
        # çakışmada boş döner.
        stmt = (
            pg_insert(invitation_accept_idempotency_table)
            .values(
                id=record_id,
                tenant_id=record.tenant_id,
                actor_user_id=record.actor_user_id,
                idempotency_key=record.idempotency_key,
                request_fingerprint=record.request_fingerprint,
                invitation_id=record.invitation_id,
                membership_id=record.membership_id,
                response_role=record.response_role,
                response_status=record.response_status,
                response_duplicate=record.response_duplicate,
                created_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "actor_user_id", "idempotency_key"]
            )
            .returning(invitation_accept_idempotency_table.c.id)
        )
        inserted = self._session.execute(stmt).first() is not None
        self._session.flush()
        return inserted
