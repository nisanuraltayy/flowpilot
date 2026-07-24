"""Production/staging yapılandırma fail-fast testleri (FP-OPS-001).

Kurallar:
- staging/production'da eksik zorunlu yapılandırma SESSİZCE kabul edilmez.
- APP_DEBUG staging/production'da açılamaz (stack trace / iç detay sızdırır).
- production'da local adres (localhost/127.0.0.1) kabul edilmez.
- Hata mesajları YALNIZ değişken ADI içerir; secret DEĞERİ asla içermez.
- local/test ortamının mevcut davranışı BOZULMAZ.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from flowpilot.api.main import create_app
from flowpilot.config.settings import Settings

_REMOTE_DB = "postgresql+psycopg://flowpilot_app:pw@db.internal.example:5432/flowpilot"
_REMOTE_SUPABASE = "https://project.supabase.co"
# FP-OPS-003A: strict ortamda API_TRUSTED_HOSTS da zorunludur. Bu sabit,
# başka bir alanın davranışını test eden senaryolara "geçerli" değer sağlar.
_TRUSTED_HOSTS = "api.example.test"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"_env_file": None}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------- eksik yapılandırma


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_missing_required_configuration_fails_fast(environment: str) -> None:
    with pytest.raises(RuntimeError) as exc:
        create_app(settings=_settings(app_environment=environment))

    message = str(exc.value)
    assert "SUPABASE_URL" in message
    assert "DATABASE_URL" in message


@pytest.mark.parametrize("environment", ["local", "test", "development"])
def test_non_strict_environments_start_without_configuration(environment: str) -> None:
    """Local/test davranışı korunur — eksik yapılandırma import'u bozmaz."""
    app = create_app(settings=_settings(app_environment=environment))
    assert app is not None


# --------------------------------------------------------------------- APP_DEBUG


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_debug_mode_is_rejected_in_strict_environments(environment: str) -> None:
    with pytest.raises(RuntimeError) as exc:
        create_app(
            settings=_settings(
                app_environment=environment,
                app_debug=True,
                database_url=SecretStr(_REMOTE_DB),
                supabase_url=_REMOTE_SUPABASE,
            )
        )

    assert "APP_DEBUG" in str(exc.value)


def test_debug_mode_is_allowed_locally() -> None:
    app = create_app(settings=_settings(app_environment="local", app_debug=True))
    assert app is not None


# ------------------------------------------------------------------ local adresler


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://flowpilot_app:pw@localhost:5432/flowpilot",
        "postgresql+psycopg://flowpilot_app:pw@127.0.0.1:5432/flowpilot",
    ],
)
def test_local_database_url_is_rejected_in_production(database_url: str) -> None:
    with pytest.raises(RuntimeError) as exc:
        create_app(
            settings=_settings(
                app_environment="production",
                database_url=SecretStr(database_url),
                supabase_url=_REMOTE_SUPABASE,
                api_trusted_hosts=_TRUSTED_HOSTS,
            )
        )

    assert "DATABASE_URL" in str(exc.value)


def test_local_supabase_url_is_rejected_in_production() -> None:
    with pytest.raises(RuntimeError) as exc:
        create_app(
            settings=_settings(
                app_environment="production",
                database_url=SecretStr(_REMOTE_DB),
                supabase_url="http://localhost:54321",
                api_trusted_hosts=_TRUSTED_HOSTS,
            )
        )

    assert "SUPABASE_URL" in str(exc.value)


def test_staging_allows_local_addresses() -> None:
    """Staging aynı host üzerinde private bağlantı kullanabilir — kontrol production'a özel."""
    app = create_app(
        settings=_settings(
            app_environment="staging",
            database_url=SecretStr("postgresql+psycopg://flowpilot_app:pw@localhost:5432/fp"),
            supabase_url=_REMOTE_SUPABASE,
            api_trusted_hosts=_TRUSTED_HOSTS,
        )
    )
    assert app is not None


# ------------------------------------------------------------------------- başarı


def test_valid_production_configuration_starts() -> None:
    app = create_app(
        settings=_settings(
            app_environment="production",
            app_debug=False,
            database_url=SecretStr(_REMOTE_DB),
            supabase_url=_REMOTE_SUPABASE,
            api_trusted_hosts=_TRUSTED_HOSTS,
        )
    )
    assert app is not None


# --------------------------------------------------------------------- secret sızıntısı


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_error_messages_never_contain_secret_values(environment: str) -> None:
    """Hata mesajı bağlantı dizesini / parolayı ASLA taşımaz."""
    with pytest.raises(RuntimeError) as exc:
        create_app(
            settings=_settings(
                app_environment=environment,
                app_debug=True,
                database_url=SecretStr(_REMOTE_DB),
                supabase_url=_REMOTE_SUPABASE,
            )
        )

    message = str(exc.value)
    assert _REMOTE_DB not in message
    assert "pw" not in message.split()
    assert "flowpilot_app:pw" not in message
