"""UserDirectory cross-module contract'ının SQLAlchemy adapter'ı.

Organization gibi diğer modüller kullanıcı varlığını bu adapter üzerinden
sorgular. Her sorgu kısa ömürlü bir session açar; import'ta engine oluşmaz.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.identity.infrastructure.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from flowpilot.shared.identifiers import UserId


class SqlAlchemyUserDirectory:
    """`UserDirectory` contract'ını uygular (salt-okunur)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def exists(self, user_id: UserId) -> bool:
        with self._session_factory() as session:
            return SqlAlchemyUserRepository(session).exists(user_id)
