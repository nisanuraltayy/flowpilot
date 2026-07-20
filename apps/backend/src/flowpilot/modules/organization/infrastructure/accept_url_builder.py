"""`InvitationAcceptUrlBuilder` adapter'ı — kabul URL'ini config'ten üretir.

Kabul akışı (Dilim B) frontend'de HENÜZ YOK; ancak API cevabı gelecekte kullanılacak
güvenli linki döndürür:

    /invitations/accept?org=<tenant_id>&token=<raw_token>

Base frontend URL `Settings.frontend_base_url`'den gelir. HARD-CODED localhost/tunnel
adresi YAZILMAZ; base yoksa host'suz relative path döner (proje config kuralı).
Ham token yalnız bu cevap için URL'e girer; log/audit/outbox'a yazılmaz.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode
from uuid import UUID

_ACCEPT_PATH = "/invitations/accept"


class SettingsInvitationAcceptUrlBuilder:
    """`InvitationAcceptUrlBuilder` port'unu uygular."""

    def __init__(self, frontend_base_url: str | None) -> None:
        # Sondaki '/' normalize edilir; None ise relative path üretilir.
        self._base = frontend_base_url.rstrip("/") if frontend_base_url else None

    def build(self, *, tenant_id: UUID, raw_token: str) -> str:
        query = urlencode({"org": str(tenant_id), "token": raw_token}, quote_via=quote)
        return f"{self._base}{_ACCEPT_PATH}?{query}" if self._base else f"{_ACCEPT_PATH}?{query}"
