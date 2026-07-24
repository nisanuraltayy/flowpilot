"""FastAPI composition root.

Kurallar (ADR-003, ADR-009):
- Burada İŞ MANTIĞI BULUNMAZ. Yetki kararı, koşul değerlendirmesi, onay sırası
  ve state transition `flowpilot.modules.*` içindedir.
- Router registration YALNIZ burada; adapter wiring `api/deps.py`'dedir.
- Import sırasında database veya Supabase bağlantısı KURULMAZ.
- Staging/production'da eksik auth/DB yapılandırması SESSİZCE kabul edilmez —
  uygulama başlangıçta açık hata ile durur. Local/test'te eksik yapılandırma
  import'u ve health endpoint'lerini bozmaz (auth gerektiren istekler 503 alır).
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from flowpilot.api.routes import (
    approval_roles,
    approval_tasks,
    health,
    invitation_access,
    invitations,
    me,
    members,
    organizations,
    purchase_requests,
    tasks,
)
from flowpilot.api.security_headers import SecurityHeadersMiddleware
from flowpilot.config.settings import Settings, get_settings

_STRICT_CONFIG_ENVIRONMENTS = ("staging", "production")

# Yalnız gerçek production'da reddedilen local adresler. Staging bazen aynı host
# üzerinde private bir bağlantı kullanabilir; bu yüzden kontrol production'a özeldir.
_LOCAL_HOST_MARKERS = ("localhost", "127.0.0.1", "::1")

# Container/platform healthcheck'leri loopback üzerinden gelir (Dockerfile
# HEALTHCHECK → http://127.0.0.1:<port>/health/live). Strict ortamlarda bu
# host'lar allowlist'e DAHİLİ olarak eklenir ki healthcheck asla kırılmasın.
# Managed provider'ın internal probe hostname'i TAHMİN EDİLMEZ; gerekirse
# API_TRUSTED_HOSTS içine açıkça eklenir (docs/operations/http-security.md).
_IMPLICIT_HEALTHCHECK_HOSTS = ("localhost", "127.0.0.1", "::1")


def _has_local_host(value: str) -> bool:
    """Bağlantı dizesi local bir host'a mı işaret ediyor (değer LOGLANMAZ)."""
    lowered = value.lower()
    return any(marker in lowered for marker in _LOCAL_HOST_MARKERS)


def _validate_runtime_configuration(settings: Settings) -> None:
    """Staging/production'da eksik veya güvensiz yapılandırmayı SESSİZCE kabul etme.

    Hata mesajlarında YALNIZ değişken ADI geçer; secret değeri hiçbir zaman yazılmaz.
    """
    if settings.app_environment not in _STRICT_CONFIG_ENVIRONMENTS:
        return

    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", settings.supabase_url),
            ("DATABASE_URL", settings.database_url),
        )
        if value is None
    ]
    if missing:
        raise RuntimeError(
            f"{settings.app_environment} ortaminda zorunlu yapilandirma eksik: "
            f"{', '.join(missing)}. Uygulama guvenli sekilde baslatilmadi."
        )

    # Debug modu staging/production'da AÇILAMAZ: stack trace ve iç detay sızdırır.
    if settings.app_debug:
        raise RuntimeError(
            f"APP_DEBUG={settings.app_debug} {settings.app_environment} ortaminda kabul "
            "edilmez. Uygulama guvenli sekilde baslatilmadi."
        )

    # TrustedHost allowlist'i strict ortamda ZORUNLUDUR (FP-OPS-003A). Hata
    # mesajı yalnız değişken ADINI söyler; host listesi/degerler yazılmaz.
    trusted_hosts = settings.trusted_host_allowlist
    if not trusted_hosts:
        raise RuntimeError(
            f"{settings.app_environment} ortaminda API_TRUSTED_HOSTS zorunludur "
            "(virgulle ayrilmis host listesi). Uygulama guvenli sekilde baslatilmadi."
        )
    if "*" in trusted_hosts:
        raise RuntimeError(
            f"API_TRUSTED_HOSTS {settings.app_environment} ortaminda bare '*' iceremez; "
            "acik host listesi gerekir. Uygulama guvenli sekilde baslatilmadi."
        )

    # Production'da local adres = yanlislikla development yapilandirmasiyla acilis.
    if settings.app_environment == "production":
        local = [
            name
            for name, value in (
                ("DATABASE_URL", settings.require_database_url()),
                ("SUPABASE_URL", settings.supabase_url or ""),
            )
            if _has_local_host(value)
        ]
        if local:
            raise RuntimeError(
                f"production ortaminda local adres kullanilamaz: {', '.join(local)}. "
                "Uygulama guvenli sekilde baslatilmadi."
            )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory.

    Args:
        settings: Enjekte edilebilir ayarlar. Verilmezse `get_settings()` kullanılır.
            Testler bu parametre sayesinde global duruma dokunmadan çalışır.
    """
    resolved = settings or get_settings()
    _validate_runtime_configuration(resolved)
    strict = resolved.app_environment in _STRICT_CONFIG_ENVIRONMENTS

    # Staging/production'da /docs, /redoc ve /openapi.json TAMAMEN kapalıdır
    # (404). Açma flag'i BİLİNÇLİ olarak yoktur; sözleşme repo'dadır ve OpenAPI
    # koddan offline üretilebilir. Local/test/development'ta açık kalır.
    app = FastAPI(
        title=resolved.app_name,
        version="0.1.0",
        debug=resolved.app_debug,
        docs_url=None if strict else "/docs",
        redoc_url=None if strict else "/redoc",
        openapi_url=None if strict else "/openapi.json",
    )
    app.state.settings = resolved

    # --- HTTP hardening (FP-OPS-003A) -----------------------------------------
    # `add_middleware` listenin BAŞINA ekler; SON eklenen EN DIŞTA çalışır.
    # TrustedHost önce eklenir, SecurityHeaders sonra → SecurityHeaders,
    # TrustedHost'un 400 yanıtını da sarar (400'de de header'lar bulunur).
    trusted_hosts = list(resolved.trusted_host_allowlist)
    if strict:
        # Loopback healthcheck'leri her zaman izinlidir (bkz. _IMPLICIT_HEALTHCHECK_HOSTS).
        trusted_hosts += [h for h in _IMPLICIT_HEALTHCHECK_HOSTS if h not in trusted_hosts]
    if trusted_hosts:
        # Non-strict ortamda YALNIZ açıkça yapılandırılmışsa eklenir; boşsa
        # middleware yoktur ve mevcut local/test davranışı aynen korunur.
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)
    app.add_middleware(SecurityHeadersMiddleware)

    # Router registration — composition root'un tek görevi.
    app.include_router(health.router)
    app.include_router(organizations.router)
    app.include_router(me.router)
    app.include_router(invitations.router)
    app.include_router(invitation_access.router)
    app.include_router(members.router)
    app.include_router(approval_roles.router)
    app.include_router(approval_tasks.router)
    app.include_router(purchase_requests.router)
    app.include_router(tasks.router)

    return app


app = create_app()
