"""SQLAlchemy Core tabanlı UserRepository adapter'ı.

`UserRepository` (modül-içi port) ve `UserDirectory` (cross-module contract)
YAPISAL olarak bu sınıfla karşılanır. Session dışarıdan enjekte edilir; import
sırasında engine oluşturulmaz.

`add`, uq(auth_provider, provider_subject) ihlalini
`DuplicateProviderIdentityError`'a çevirir — yarış koruması DB'dedir.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Row, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from flowpilot.modules.identity.application.errors import DuplicateProviderIdentityError
from flowpilot.modules.identity.domain.auth_provider import AuthProvider
from flowpilot.modules.identity.domain.user import User
from flowpilot.modules.identity.infrastructure.persistence.tables import users_table
from flowpilot.shared.identifiers import UserId


def _row_to_user(row: Row[Any]) -> User:
    return User(
        id=UserId(row.id),
        auth_provider=AuthProvider(row.auth_provider) if row.auth_provider else None,
        provider_subject=row.provider_subject,
        email_snapshot=row.email_snapshot,
        created_at=row.created_at,
    )


class SqlAlchemyUserRepository:
    """`UserRepository` ve `UserDirectory` port'larını uygular."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: User) -> None:
        try:
            self._session.execute(
                insert(users_table).values(
                    id=user.id.value,
                    auth_provider=user.auth_provider.value if user.auth_provider else None,
                    provider_subject=user.provider_subject,
                    email_snapshot=user.email_snapshot,
                    created_at=user.created_at,
                )
            )
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateProviderIdentityError() from exc

    def exists(self, user_id: UserId) -> bool:
        result = self._session.execute(
            select(users_table.c.id).where(users_table.c.id == user_id.value)
        ).first()
        return result is not None

    def find_by_provider_identity(
        self, provider: AuthProvider, provider_subject: str
    ) -> User | None:
        row = self._session.execute(
            select(users_table).where(
                users_table.c.auth_provider == provider.value,
                users_table.c.provider_subject == provider_subject,
            )
        ).first()
        return _row_to_user(row) if row is not None else None

    def find_user_ids_by_email(self, email: str) -> list[UUID]:
        # email_snapshot benzersiz DEĞİLDİR ve nullable'dır → 0/1/çok satır olabilir.
        # Karşılaştırma normalize (lower) yapılır; NULL snapshot'lar eşleşmez.
        rows = (
            self._session.execute(
                select(users_table.c.id).where(
                    func.lower(users_table.c.email_snapshot) == email.strip().lower()
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    def find_email_snapshot(self, user_id: UserId) -> str | None:
        row = self._session.execute(
            select(users_table.c.email_snapshot).where(users_table.c.id == user_id.value)
        ).first()
        return row[0] if row is not None else None
