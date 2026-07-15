"""Identity application port'ları (modül-içi)."""

from __future__ import annotations

from typing import Protocol

from flowpilot.modules.identity.domain.user import User
from flowpilot.shared.identifiers import UserId


class UserRepository(Protocol):
    """Kullanıcı persistence port'u.

    `add`, ileride Supabase adapter'ının ilk girişte kullanıcıyı FlowPilot'a
    yazması için de kullanılacaktır. Bu aşamada testler actor kullanıcıyı
    bununla oluşturur.
    """

    def add(self, user: User) -> None: ...

    def exists(self, user_id: UserId) -> bool: ...
