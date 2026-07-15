"""Provider-neutral authentication sözleşmesi (application boundary).

`AuthProviderPort` raw access token'ı alır ve doğrulanmış `AuthenticatedIdentity`
döndürür. RAW TOKEN BU SINIRIN ÖTESİNE GEÇMEZ: domain ve use-case'ler yalnız
doğrulanmış kimliği görür. Token hiçbir exception mesajına, repr'e veya log'a
YAZILMAZ.

Supabase'e özgü claim adları burada DEĞİL, infrastructure adapter'ında
normalize edilir (ADR-005).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from flowpilot.modules.identity.domain.auth_provider import AuthProvider
from flowpilot.shared.errors import DomainError


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """Doğrulanmış harici kimlik — token değil, tokenın KANITLADIĞI kimlik.

    `provider_subject` internal user ID olarak KULLANILMAZ; yalnız eşleme
    anahtarıdır. `email` opsiyoneldir ve primary identity değildir.
    """

    provider: AuthProvider
    provider_subject: str
    email: str | None
    token_expires_at: datetime


class AuthenticationError(DomainError):
    """Authentication hatalarının temel sınıfı. Token içeriği TAŞIMAZ."""


class InvalidAccessToken(AuthenticationError):
    """Token geçersiz: imza, issuer, audience, algoritma veya claim hatası."""

    def __init__(self) -> None:
        super().__init__("Access token gecersiz.")


class ExpiredAccessToken(AuthenticationError):
    """Token süresi dolmuş."""

    def __init__(self) -> None:
        super().__init__("Access token suresi dolmus.")


class AuthProviderUnavailable(AuthenticationError):
    """Provider/JWKS geçici olarak erişilemiyor.

    Bu INVALID-TOKEN DEĞİLDİR: istemci hatası değil, geçici altyapı hatasıdır
    ve HTTP katmanında 401 değil 503'e eşlenir.
    """

    def __init__(self) -> None:
        super().__init__("Kimlik saglayicisina su anda erisilemiyor.")


class AuthProviderPort(Protocol):
    """Access token doğrulama port'u.

    Raises:
        InvalidAccessToken: imza/issuer/audience/claim/algoritma hatası.
        ExpiredAccessToken: süresi dolmuş token.
        AuthProviderUnavailable: JWKS/provider'a geçici erişim hatası.
    """

    def verify_token(self, access_token: str) -> AuthenticatedIdentity: ...
