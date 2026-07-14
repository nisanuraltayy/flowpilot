"""Uygulama ayarları.

Kurallar (ADR-009, .claude/rules/security.md):
- Ayarlar environment değişkenlerinden yüklenir.
- Import sırasında gerçek secret ZORUNLU DEĞİLDİR; uygulama local ve test
  ortamında secret olmadan import edilebilir.
- MUTABLE GLOBAL SETTINGS NESNESİ YOKTUR. Erişim `get_settings()` üzerindendir.
- `Settings` frozen'dır; bir kez oluşturulur, değiştirilemez.
- Secret alanları ileride `SecretStr` ile eklenir; `model_config` bu yüzden
  repr/log sızıntısına karşı şimdiden güvenlidir (bkz. tests/unit/test_settings.py).

Bu aşamada PostgreSQL, Supabase ve object storage ayarları BİLİNÇLİ OLARAK YOKTUR.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
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

    app_name: str = "FlowPilot"
    app_environment: Environment = "local"
    app_debug: bool = False
    log_level: LogLevel = "info"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ayarları oluşturur ve cache'ler.

    Cache, süreç ömrü boyunca tek bir immutable örnek döndürür. Bu bir *mutable
    global* değildir: `Settings` frozen'dır ve testler `get_settings.cache_clear()`
    ile cache'i temizleyip environment override'larını doğrulayabilir.
    """
    return Settings()
