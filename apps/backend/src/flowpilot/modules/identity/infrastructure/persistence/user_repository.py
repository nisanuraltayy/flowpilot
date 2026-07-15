"""SQLAlchemy Core tabanlı UserRepository adapter'ı.

`UserRepository` (modül-içi port) ve `UserDirectory` (cross-module contract)
YAPISAL olarak bu sınıfla karşılanır: her ikisi de `exists(...)` bekler.
Session dışarıdan enjekte edilir; import sırasında engine oluşturulmaz.
"""

from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from flowpilot.modules.identity.domain.user import User
from flowpilot.modules.identity.infrastructure.persistence.tables import users_table
from flowpilot.shared.identifiers import UserId


class SqlAlchemyUserRepository:
    """`UserRepository` ve `UserDirectory` port'larını uygular."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: User) -> None:
        self._session.execute(
            insert(users_table).values(
                id=user.id.value,
                email=user.email,
                external_auth_subject=user.external_auth_subject,
                created_at=user.created_at,
            )
        )
        self._session.flush()

    def exists(self, user_id: UserId) -> bool:
        result = self._session.execute(
            select(users_table.c.id).where(users_table.c.id == user_id.value)
        ).first()
        return result is not None
