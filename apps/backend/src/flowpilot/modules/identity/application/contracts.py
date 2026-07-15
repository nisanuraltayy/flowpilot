"""Identity'nin dışarıya açtığı CROSS-MODULE application contract'ı.

Başka modüller (ör. organization), bir kullanıcının var olup olmadığını YALNIZCA
bu açık contract üzerinden sorar — identity'nin domain veya infrastructure
katmanını DOĞRUDAN import ETMEZ (domain-boundaries.md, ADR-009).
"""

from __future__ import annotations

from typing import Protocol

from flowpilot.shared.identifiers import UserId


class UserDirectory(Protocol):
    """Kullanıcı varlığını sorgulayan salt-okunur cross-module contract."""

    def exists(self, user_id: UserId) -> bool: ...
