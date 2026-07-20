"""UserDirectory cross-module contract'ının SQLAlchemy adapter'ı.

Organization gibi diğer modüller kullanıcı varlığını bu adapter üzerinden
sorgular. Her sorgu kısa ömürlü bir session açar; import'ta engine oluşmaz.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.identity.infrastructure.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from flowpilot.shared.identifiers import UserId


class SqlAlchemyUserDirectory:
    """`UserDirectory` ve `UserEmailLookup` contract'larını uygular (salt-okunur)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def exists(self, user_id: UserId) -> bool:
        with self._session_factory() as session:
            return SqlAlchemyUserRepository(session).exists(user_id)

    def find_user_ids_by_email(self, email: str) -> list[UUID]:
        with self._session_factory() as session:
            return SqlAlchemyUserRepository(session).find_user_ids_by_email(email)

    def find_email_snapshot(self, user_id: UserId) -> str | None:
        with self._session_factory() as session:
            return SqlAlchemyUserRepository(session).find_email_snapshot(user_id)
