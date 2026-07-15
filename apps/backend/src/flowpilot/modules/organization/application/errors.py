"""Organization application-katmanı error'ları.

Domain doğrulama hataları buradan RE-EXPORT edilir: composition root (api)
modüllerin domain katmanını doğrudan import EDEMEZ (ADR-009); hata eşlemesi
için application sınırındaki bu isimleri kullanır.
"""

from __future__ import annotations

from uuid import UUID

from flowpilot.modules.organization.domain.errors import (
    EmptyOrganizationNameError as EmptyOrganizationNameError,
)
from flowpilot.modules.organization.domain.errors import (
    OrganizationNameError as OrganizationNameError,
)
from flowpilot.modules.organization.domain.errors import (
    OrganizationNameTooLongError as OrganizationNameTooLongError,
)
from flowpilot.shared.errors import DomainError


class ActorNotFoundError(DomainError):
    """Organizasyonu oluşturmaya çalışan actor kullanıcı bulunamadı."""

    def __init__(self, actor_user_id: UUID) -> None:
        super().__init__(f"Actor kullanici bulunamadi: {actor_user_id}")
        self.actor_user_id = actor_user_id
