"""Identity application port'ları (modül-içi)."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

from flowpilot.modules.identity.domain.auth_provider import AuthProvider
from flowpilot.modules.identity.domain.user import User
from flowpilot.shared.identifiers import UserId


class UserRepository(Protocol):
    """Kullanıcı persistence port'u.

    `add`, aynı (provider, subject) için ikinci kayıtta
    `DuplicateProviderIdentityError` fırlatır (DB unique constraint çevirisi).
    """

    def add(self, user: User) -> None: ...

    def exists(self, user_id: UserId) -> bool: ...

    def find_by_provider_identity(
        self, provider: AuthProvider, provider_subject: str
    ) -> User | None: ...


class IdentityUnitOfWork(Protocol):
    """Identity modülünün transaction sınırı.

    identity_users GLOBAL bir tablodur (RLS yok) — tenant context gerekmez.
    """

    users: UserRepository

    def __enter__(self) -> IdentityUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
