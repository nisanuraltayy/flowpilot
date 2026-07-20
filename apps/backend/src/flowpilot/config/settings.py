"""Uygulama ayarları.

Kurallar (ADR-009, .claude/rules/security.md):
- Ayarlar environment değişkenlerinden yüklenir.
- Import sırasında gerçek secret ZORUNLU DEĞİLDİR; uygulama local ve test
  ortamında secret olmadan import edilebilir. Bu yüzden database URL alanları
  Optional'dır (None default) — eksiklerse `require_*` yardımcıları anlaşılır
  hata verir.
- MUTABLE GLOBAL SETTINGS NESNESİ YOKTUR. Erişim `get_settings()` üzerindendir.
- `Settings` frozen'dır; bir kez oluşturulur, değiştirilemez.
- Secret alanları `SecretStr`'dir; repr/log'da maskelenir.
- Import sırasında hiçbir database bağlantısı açılmaz.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "development", "staging", "production"]
LogLevel = Literal["debug", "info", "warning", "error", "critical"]


class Settings(BaseSettings):
    """Environment'tan yüklenen, değiştirilemez uygulama ayarları."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    # --- Uygulama ---
    app_name: str = "FlowPilot"
    app_environment: Environment = "local"
    app_debug: bool = False
    log_level: LogLevel = "info"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    # Frontend public base URL — davet kabul linki (accept_url) bundan üretilir.
    # HARD-CODE EDİLMEZ; env'den gelir. Yoksa relative path (host'suz) üretilir —
    # sahte localhost/tunnel adresi yazılmaz.
    frontend_base_url: str | None = None

    # --- Database (Optional — import/secret zorunluluğu yok) ---
    # Uygulama bağlantısı: BYPASSRLS'siz `flowpilot_app` rolü (ADR-006).
    database_url: SecretStr | None = None
    # Migration bağlantısı: DDL yetkili `flowpilot_migrator` rolü — app'ten AYRI.
    migration_database_url: SecretStr | None = None

    # --- Supabase Auth (ADR-005 — YALNIZ JWT doğrulama) ---
    # Public proje URL'i — secret DEĞİLDİR (SecretStr yapılmaz). JWKS URL'i ve
    # issuer bundan türetilir. SERVICE ROLE KEY ve JWT SECRET BİLİNÇLİ OLARAK
    # YOKTUR: doğrulama yalnız public JWKS iledir.
    supabase_url: str | None = None
    supabase_jwt_audience: str = "authenticated"
    # Virgülle ayrılmış allow-list; yalnız asimetrik algoritmalar (HS* reddedilir).
    supabase_jwt_allowed_algorithms: str = "RS256,ES256"
    supabase_jwks_cache_seconds: int = Field(default=300, ge=1)
    supabase_jwks_timeout_seconds: float = Field(default=5.0, gt=0)

    @property
    def supabase_issuer(self) -> str | None:
        """JWT issuer: <SUPABASE_URL>/auth/v1 (URL'den güvenli türetilir)."""
        if self.supabase_url is None:
            return None
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str | None:
        """Public JWKS adresi: <issuer>/.well-known/jwks.json."""
        issuer = self.supabase_issuer
        return f"{issuer}/.well-known/jwks.json" if issuer else None

    @property
    def supabase_allowed_algorithms(self) -> tuple[str, ...]:
        """Virgülle ayrılmış algoritma listesini normalize eder."""
        return tuple(
            item.strip() for item in self.supabase_jwt_allowed_algorithms.split(",") if item.strip()
        )

    def require_database_url(self) -> str:
        """Uygulama bağlantı dizesini döndürür; yoksa anlaşılır hata verir."""
        if self.database_url is None:
            raise RuntimeError(
                "DATABASE_URL tanimli degil. Repo kokunde .env olusturun "
                "(.env.example §2). Uygulama rolu: flowpilot_app (BYPASSRLS yok)."
            )
        return self.database_url.get_secret_value()

    def require_migration_database_url(self) -> str:
        """Migration bağlantı dizesini döndürür; yoksa anlaşılır hata verir."""
        if self.migration_database_url is None:
            raise RuntimeError(
                "MIGRATION_DATABASE_URL tanimli degil. Repo kokunde .env olusturun "
                "(.env.example §2). Migration rolu: flowpilot_migrator."
            )
        return self.migration_database_url.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ayarları oluşturur ve cache'ler.

    Cache, süreç ömrü boyunca tek bir immutable örnek döndürür. Bu bir *mutable
    global* değildir: `Settings` frozen'dır ve testler `get_settings.cache_clear()`
    ile cache'i temizleyip environment override'larını doğrulayabilir.
    """
    return Settings()
