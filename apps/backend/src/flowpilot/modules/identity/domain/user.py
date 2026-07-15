"""User — FlowPilot'ın iç kullanıcı kaydı.

Kimlik eşlemesi: `(auth_provider, provider_subject)` çifti harici kimliği
FlowPilot user'ına bağlar (DB'de unique). Internal `UserId` UUID'si provider
subject'ten BAĞIMSIZDIR ve asla onun yerine kullanılmaz.

- `email_snapshot` yalnız görüntüleme kolaylığı için tutulan, provider'dan
  gelen SON bilinen e-postadır. PRIMARY IDENTITY DEĞİLDİR (PRD §34.1); e-posta
  değişse bile aynı internal user korunur.
- Login, parola, session, refresh token BURADA YOKTUR ve saklanmaz (ADR-005).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from flowpilot.modules.identity.domain.auth_provider import AuthProvider
from flowpilot.shared.identifiers import UserId


@dataclass(frozen=True)
class User:
    """Bir FlowPilot kullanıcısı."""

    id: UserId
    auth_provider: AuthProvider | None
    provider_subject: str | None
    email_snapshot: str | None
    created_at: datetime

    @classmethod
    def from_external_identity(
        cls,
        *,
        id: UserId,
        auth_provider: AuthProvider,
        provider_subject: str,
        email_snapshot: str | None,
        created_at: datetime,
    ) -> User:
        """Doğrulanmış harici kimlikten yeni internal user oluşturur."""
        return cls(
            id=id,
            auth_provider=auth_provider,
            provider_subject=provider_subject,
            email_snapshot=email_snapshot,
            created_at=created_at,
        )
