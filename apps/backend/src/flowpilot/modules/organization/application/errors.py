"""Organization application-katmanı error'ları."""

from __future__ import annotations

from uuid import UUID

from flowpilot.shared.errors import DomainError


class ActorNotFoundError(DomainError):
    """Organizasyonu oluşturmaya çalışan actor kullanıcı bulunamadı."""

    def __init__(self, actor_user_id: UUID) -> None:
        super().__init__(f"Actor kullanici bulunamadi: {actor_user_id}")
        self.actor_user_id = actor_user_id
