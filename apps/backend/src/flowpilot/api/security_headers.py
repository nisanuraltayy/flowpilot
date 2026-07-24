"""Temel API security response header'ları (FP-OPS-003A).

Saf ASGI middleware — iş mantığı İÇERMEZ (ADR-003: composition root katmanı).
Body/status DEĞİŞTİRİLMEZ; yalnız eksik header'lar eklenir. Streaming davranışı
bozulmaz: header'lar `http.response.start` mesajında eklenir, body mesajlarına
dokunulmaz.

Eklenen header'lar (yalnız response'ta ZATEN YOKSA — duplicate üretilmez ve
endpoint'in açıkça koyduğu değer korunur):

- ``X-Content-Type-Options: nosniff``
- ``Referrer-Policy: no-referrer``
- ``Cache-Control: no-store``  (API yanıtları Confidential sınıfıdır; cache'lenmez)

Bilinen sınır: Starlette'in en dıştaki ``ServerErrorMiddleware``'i UNHANDLED
exception 500 yanıtını bu middleware'in send wrapper'ı DEVREYE GİRMEDEN üretir;
o yanıt bu header'ları taşımaz. Generic 500 handler bilinçli olarak bu dilimde
EKLENMEMİŞTİR (bkz. docs/operations/http-security.md). Handled hatalar (401/404/
409/422/503, TrustedHost 400 dahil) bu middleware'den geçer.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

# (küçük-harf ad, değer) — HTTP header adları case-insensitive karşılaştırılır.
_SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
)


class SecurityHeadersMiddleware:
    """Her HTTP yanıtına eksik temel güvenlik header'larını ekler."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers") or [])
                existing = {name.lower() for name, _ in headers}
                for name, value in _SECURITY_HEADERS:
                    if name not in existing:
                        headers.append((name, value))
                message["headers"] = headers
            await send(message)

        await self._app(scope, receive, send_with_headers)
