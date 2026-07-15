"""Clock port'u — domain içinde doğrudan sistem saati okumak YASAK (FF-12).

Testlerde fake clock kullanılabilmelidir. Tüm zaman UTC'dir (PRD §34.1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class ClockPort(Protocol):
    """Şimdiki UTC zamanını döndüren port."""

    def now(self) -> datetime: ...


class SystemClock:
    """Gerçek sistem saatini UTC olarak döndürür."""

    def now(self) -> datetime:
        return datetime.now(tz=UTC)
