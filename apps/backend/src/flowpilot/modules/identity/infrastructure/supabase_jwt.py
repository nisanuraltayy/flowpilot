"""SupabaseJwtAuthAdapter — Supabase access token'ını public JWKS ile doğrular.

Güvenlik kararları (ADR-005, .claude/rules/security.md §2):

- Doğrulama YALNIZ public JWKS iledir: <SUPABASE_URL>/auth/v1/.well-known/jwks.json
  Service role key KULLANILMAZ; Supabase database'ine BAĞLANILMAZ; tam supabase
  SDK'sı YOKTUR (yalnız PyJWT + cryptography).
- Algoritma allow-list AÇIKTIR ve yalnız ASİMETRİK algoritmalara izin verilir.
  HS* (shared secret) construction anında REDDEDİLİR. `algorithms` değeri token
  header'ından ASLA alınmaz.
- Doğrulananlar: imza, exp, iat, iss (<SUPABASE_URL>/auth/v1), aud
  (varsayılan "authenticated"), sub zorunlu.
- JWKS erişim hatası InvalidAccessToken DEĞİL, ayrı `AuthProviderUnavailable`
  hatasıdır (HTTP 503'e eşlenir) — geçici altyapı hatası istemci hatası gibi
  gösterilmez.
- Public key cache + key rotation: PyJWKClient (lifespan = cache saniyesi).
- RAW TOKEN hiçbir exception mesajına, log'a veya repr'e YAZILMAZ.
- Supabase'e özgü claim adları BURADA normalize edilir; application katmanı
  yalnız `AuthenticatedIdentity` görür.
"""

from __future__ import annotations

from datetime import UTC, datetime

import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidTokenError,
    PyJWKClientConnectionError,
    PyJWKClientError,
)

from flowpilot.modules.identity.application.auth import (
    AuthenticatedIdentity,
    AuthProviderUnavailable,
    ExpiredAccessToken,
    InvalidAccessToken,
)
from flowpilot.modules.identity.domain.auth_provider import AuthProvider

# Yalnız asimetrik algoritmalar. HS* bilinçli olarak YOKTUR: shared-secret
# doğrulama, secret'in API tarafında saklanmasını gerektirir ve anahtar
# sızıntısında token SAHTELENEBİLİR. Public-key doğrulamada böyle bir risk yok.
_ASYMMETRIC_ALGORITHMS = frozenset(
    {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"}
)

_REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub"]


class SupabaseJwtAuthAdapter:
    """`AuthProviderPort`'un Supabase JWT implementasyonu."""

    def __init__(
        self,
        *,
        supabase_url: str,
        audience: str = "authenticated",
        allowed_algorithms: tuple[str, ...] = ("RS256", "ES256"),
        jwks_cache_seconds: int = 300,
        jwks_timeout_seconds: float = 5.0,
        jwk_client: PyJWKClient | None = None,
    ) -> None:
        forbidden = [a for a in allowed_algorithms if a not in _ASYMMETRIC_ALGORITHMS]
        if forbidden:
            raise ValueError(
                "Yalniz asimetrik JWT algoritmalarina izin verilir; "
                f"reddedilen: {forbidden}. HS* (shared secret) DESTEKLENMEZ."
            )
        if not allowed_algorithms:
            raise ValueError("En az bir JWT algoritmasi yapilandirilmalidir.")

        base = supabase_url.rstrip("/")
        self._issuer = f"{base}/auth/v1"
        self._audience = audience
        self._algorithms = list(allowed_algorithms)
        # Test edilebilirlik: jwk_client enjekte edilebilir (kontrollü/local JWKS).
        # Production'da gerçek PyJWKClient, public JWKS URL'inden beslenir.
        self._jwk_client = jwk_client or PyJWKClient(
            f"{self._issuer}/.well-known/jwks.json",
            cache_keys=True,
            lifespan=jwks_cache_seconds,
            timeout=jwks_timeout_seconds,
        )

    def verify_token(self, access_token: str) -> AuthenticatedIdentity:
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(access_token)
        except PyJWKClientConnectionError as exc:
            # JWKS'e ulaşılamıyor — istemci hatası DEĞİL. Token detayı taşınmaz.
            raise AuthProviderUnavailable() from exc
        except PyJWKClientError as exc:
            # kid bulunamadı / JWKS bozuk / header çözülemedi.
            raise InvalidAccessToken() from exc
        except InvalidTokenError as exc:
            # Header decode hatası (bozuk token).
            raise InvalidAccessToken() from exc

        try:
            claims = jwt.decode(
                access_token,
                key=signing_key.key,
                algorithms=self._algorithms,  # ASLA token header'ından alınmaz
                issuer=self._issuer,
                audience=self._audience,
                options={"require": _REQUIRED_CLAIMS},
            )
        except ExpiredSignatureError as exc:
            raise ExpiredAccessToken() from exc
        except InvalidTokenError as exc:
            # İmza, iss, aud, iat, eksik claim, algoritma uyumsuzluğu...
            raise InvalidAccessToken() from exc

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise InvalidAccessToken()

        email = claims.get("email")
        return AuthenticatedIdentity(
            provider=AuthProvider.SUPABASE,
            provider_subject=subject,
            email=email if isinstance(email, str) and email else None,
            token_expires_at=datetime.fromtimestamp(int(claims["exp"]), tz=UTC),
        )
