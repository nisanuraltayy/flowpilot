"""Settings testleri.

Doğrulananlar: varsayılanlar, environment override, geçersiz değerlerin reddi,
repr'in secret'a karşı güvenli olması ve MUTABLE GLOBAL SETTINGS BULUNMAMASI.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from flowpilot.config import settings as settings_module
from flowpilot.config.settings import Settings, get_settings


def test_defaults() -> None:
    s = Settings()

    assert s.app_name == "FlowPilot"
    assert s.app_environment == "local"
    assert s.app_debug is False
    assert s.log_level == "info"
    assert s.api_host == "127.0.0.1"
    assert s.api_port == 8000


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "FlowPilot-Test")
    monkeypatch.setenv("APP_ENVIRONMENT", "staging")
    monkeypatch.setenv("APP_DEBUG", "true")
    monkeypatch.setenv("LOG_LEVEL", "warning")
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    monkeypatch.setenv("API_PORT", "9001")

    s = Settings()

    assert s.app_name == "FlowPilot-Test"
    assert s.app_environment == "staging"
    assert s.app_debug is True
    assert s.log_level == "warning"
    assert s.api_host == "0.0.0.0"
    assert s.api_port == 9001


def test_invalid_app_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(app_environment="prod")  # type: ignore[arg-type]


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="verbose")  # type: ignore[arg-type]


@pytest.mark.parametrize("port", [0, -1, 65536, 99999])
def test_api_port_out_of_range_is_rejected(port: int) -> None:
    with pytest.raises(ValidationError):
        Settings(api_port=port)


def test_api_port_boundaries_are_accepted() -> None:
    assert Settings(api_port=1).api_port == 1
    assert Settings(api_port=65535).api_port == 65535


def test_settings_are_immutable() -> None:
    s = Settings()

    with pytest.raises(ValidationError):
        s.api_port = 1234  # type: ignore[misc]


def test_no_mutable_global_settings_object() -> None:
    # Modülde hazır bir `settings` örneği BULUNMAMALIDIR; erişim get_settings() ile olur.
    assert not hasattr(settings_module, "settings")

    module_level_instances = [
        name for name, value in vars(settings_module).items() if isinstance(value, Settings)
    ]
    assert module_level_instances == []


def test_get_settings_is_cached_and_returns_same_instance() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()


def test_repr_masks_secret_fields() -> None:
    # Settings'in şu an secret alanı yok. Bu test, secret alanı EKLENDİĞİNDE
    # repr'in sızdırmayacağını kanıtlar: SecretStr değeri repr'de maskelenir.
    class SettingsWithSecret(Settings):
        provider_key: SecretStr = SecretStr("super-secret-value")

    rendered = repr(SettingsWithSecret())

    assert "super-secret-value" not in rendered
    assert "**********" in rendered


# _env_file=None: repo kökündeki local .env'i yok sayar — testler ortamdan izole.


def test_database_urls_default_to_none() -> None:
    s = Settings(_env_file=None)
    assert s.database_url is None
    assert s.migration_database_url is None


def test_require_database_url_raises_when_missing() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        Settings(_env_file=None).require_database_url()


def test_require_migration_database_url_raises_when_missing() -> None:
    with pytest.raises(RuntimeError, match="MIGRATION_DATABASE_URL"):
        Settings(_env_file=None).require_migration_database_url()


def test_database_url_is_secret_and_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_url = "postgresql+psycopg://flowpilot_app:top-secret@localhost:5432/flowpilot"
    monkeypatch.setenv("DATABASE_URL", secret_url)

    s = Settings()

    assert s.require_database_url() == secret_url
    assert isinstance(s.database_url, SecretStr)
    # Parola repr'de görünmemeli.
    assert "top-secret" not in repr(s)
