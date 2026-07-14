"""Health endpoint'leri.

- Authentication ve tenant context GEREKTİRMEZ.
- İş mantığı İÇERMEZ.
- Bu aşamada readiness STATİKTİR: PostgreSQL, Supabase veya object storage
  kontrol edilmez. Gerçek bağımlılık kontrolleri ilgili story'lerde eklenecektir.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    """Süreç ayakta mı."""

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    """Süreç trafik almaya hazır mı.

    `checks` şu an boştur. Bağımlılık kontrolleri (DB, storage) eklendiğinde
    her biri buraya adlandırılmış bir sonuç olarak girer.
    """

    status: Literal["ready"] = "ready"
    checks: dict[str, str] = Field(default_factory=dict)


@router.get("/live", response_model=LivenessResponse, summary="Liveness probe")
def liveness() -> LivenessResponse:
    """Süreç canlı — hiçbir dış bağımlılık kontrol edilmez."""
    return LivenessResponse()


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
def readiness() -> ReadinessResponse:
    """Statik readiness — bu aşamada kontrol edilecek bağımlılık yoktur."""
    return ReadinessResponse()
