"""Health endpoint'leri.

- Authentication ve tenant context GEREKTİRMEZ.
- İş mantığı İÇERMEZ.
- `/health/live`: süreç ayakta mı — hiçbir dış bağımlılık kontrol EDİLMEZ.
- `/health/ready`: süreç trafik almaya hazır mı — GERÇEK database bağlantısı
  kontrol edilir (FP-OPS-002).

Readiness kuralları:
- Uygulamanın PAYLAŞILAN, cache'lenmiş session factory'si kullanılır; her istekte
  yeni engine OLUŞTURULMAZ (bkz. `deps.get_session_factory`).
- En küçük bağlantı sorgusu (`SELECT 1`) çalıştırılır; tenant context gerekmez.
- Migration/schema/seed ÇALIŞTIRILMAZ; Supabase veya object storage ÇAĞRILMAZ.
- Worker heartbeat'i API readiness'e BAĞLANMAZ.
- Hata durumunda ham exception, DSN, host, port, kullanıcı adı, parola veya stack
  trace response'a TAŞINMAZ — yalnız `failed` bilgisi döner.
- Database erişilemese bile süreç ÇÖKMEZ ve `/health/live` etkilenmez.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from flowpilot.api.deps import get_session_factory

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    """Süreç ayakta mı."""

    status: Literal["ok"] = "ok"


class ReadinessCheck(BaseModel):
    """Tek bir bağımlılığın readiness sonucu (detay/hata metni İÇERMEZ)."""

    status: Literal["ok", "failed"]


class ReadinessResponse(BaseModel):
    """Süreç trafik almaya hazır mı + bağımlılık kontrolleri."""

    status: Literal["ready", "not_ready"]
    checks: dict[str, ReadinessCheck] = Field(default_factory=dict)


@router.get("/live", response_model=LivenessResponse, summary="Liveness probe")
def liveness() -> LivenessResponse:
    """Süreç canlı — hiçbir dış bağımlılık kontrol edilmez."""
    return LivenessResponse()


def _database_is_ready(request: Request) -> bool:
    """Paylaşılan session factory ile `SELECT 1`. Hata DIŞARI SIZMAZ.

    Yapılandırma eksikse veya bağlantı kurulamazsa `False` döner; exception
    yükseltmez, böylece readiness probe'u süreci çökertmez.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return False
    try:
        session_factory = get_session_factory(request, settings)
        with session_factory() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        # Ham hata BİLİNÇLİ olarak yutulur: readiness gövdesine hiçbir teknik
        # detay (DSN/host/parola/driver mesajı/stack) taşınmaz.
        return False
    return True


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadinessResponse, "description": "Bagimlilik hazir degil"}},
)
def readiness(request: Request, response: Response) -> ReadinessResponse:
    """Gerçek database readiness — hazırsa 200, değilse 503."""
    if _database_is_ready(request):
        return ReadinessResponse(status="ready", checks={"database": ReadinessCheck(status="ok")})

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="not_ready", checks={"database": ReadinessCheck(status="failed")}
    )
