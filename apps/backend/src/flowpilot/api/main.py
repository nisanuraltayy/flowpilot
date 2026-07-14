"""FastAPI composition root.

Kurallar (ADR-003, ADR-009):
- Burada İŞ MANTIĞI BULUNMAZ. Yetki kararı, koşul değerlendirmesi, onay sırası
  ve state transition `flowpilot.modules.*` içindedir.
- Router registration ve (ileride) adapter wiring YALNIZ burada yapılır.
- Import sırasında database veya Supabase bağlantısı KURULMAZ.
"""

from __future__ import annotations

from fastapi import FastAPI

from flowpilot.api.routes import health
from flowpilot.config.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory.

    Args:
        settings: Enjekte edilebilir ayarlar. Verilmezse `get_settings()` kullanılır.
            Testler bu parametre sayesinde global duruma dokunmadan çalışır.
    """
    resolved = settings or get_settings()

    app = FastAPI(
        title=resolved.app_name,
        version="0.1.0",
        debug=resolved.app_debug,
    )
    app.state.settings = resolved

    # Router registration — composition root'un tek görevi.
    app.include_router(health.router)

    return app


app = create_app()
