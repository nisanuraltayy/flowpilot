"""SQLAlchemy tabanlı IdentityUnitOfWork adapter'ı.

identity_users GLOBAL tablodur (RLS yok) — tenant context ayarı gerekmez.
Session factory dışarıdan enjekte edilir; import sırasında engine oluşturulmaz.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from flowpilot.modules.identity.application.ports import UserRepository
from flowpilot.modules.identity.infrastructure.persistence.user_repository import (
    SqlAlchemyUserRepository,
)


class SqlAlchemyIdentityUnitOfWork:
    """`IdentityUnitOfWork` port'unu uygular."""

    users: UserRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyIdentityUnitOfWork:
        self._session = self._session_factory()
        self.users = SqlAlchemyUserRepository(self._session)
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

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork aktif degil — 'with uow:' blogu icinde kullanin.")
        return self._session
