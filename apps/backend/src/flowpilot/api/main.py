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

from flowpilot.api.routes import (
    health,
    invitation_access,
    invitations,
    me,
    organizations,
    purchase_requests,
    tasks,
)
from flowpilot.config.settings import Settings, get_settings

_STRICT_CONFIG_ENVIRONMENTS = ("staging", "production")


def _validate_runtime_configuration(settings: Settings) -> None:
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


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory.

    Args:
        settings: Enjekte edilebilir ayarlar. Verilmezse `get_settings()` kullanılır.
            Testler bu parametre sayesinde global duruma dokunmadan çalışır.
    """
    resolved = settings or get_settings()
    _validate_runtime_configuration(resolved)

    app = FastAPI(
        title=resolved.app_name,
        version="0.1.0",
        debug=resolved.app_debug,
    )
    app.state.settings = resolved

    # Router registration — composition root'un tek görevi.
    app.include_router(health.router)
    app.include_router(organizations.router)
    app.include_router(me.router)
    app.include_router(invitations.router)
    app.include_router(invitation_access.router)
    app.include_router(purchase_requests.router)
    app.include_router(tasks.router)

    return app


app = create_app()
