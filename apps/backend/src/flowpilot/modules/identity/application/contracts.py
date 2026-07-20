"""Identity'nin dışarıya açtığı CROSS-MODULE application contract'ı.

Başka modüller (ör. organization), bir kullanıcının var olup olmadığını YALNIZCA
bu açık contract üzerinden sorar — identity'nin domain veya infrastructure
katmanını DOĞRUDAN import ETMEZ (domain-boundaries.md, ADR-009).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from flowpilot.shared.identifiers import UserId


class UserDirectory(Protocol):
    """Kullanıcı varlığını sorgulayan salt-okunur cross-module contract."""

    def exists(self, user_id: UserId) -> bool: ...


class UserEmailLookup(Protocol):
    """E-posta (normalize) ile eşleşen kullanıcı ID'lerini döndüren salt-okunur contract.

    `identity_users` GLOBAL tablodur (RLS yok) ve e-posta primary key DEĞİLDİR
    (snapshot; benzersiz olmayabilir) — bu yüzden ZERO/BİR/ÇOK ID dönebilir. Çağıran
    modül bu ID'leri KENDİ tenant scope'unda membership ile kontrol eder; bu contract
    tek başına üyelik/tenant bilgisi SIZDIRMAZ.
    """

    def find_user_ids_by_email(self, email: str) -> list[UUID]: ...


class ActorEmailReader(Protocol):
    """Doğrulanmış bir actor'ın `email_snapshot` değerini okuyan salt-okunur contract.

    Davet kabulünde, actor'ın e-postasının davet e-postasıyla eşleşmesi için kullanılır.
    Snapshot NULL olabilir; o durumda davet kabul edilemez (çağıran karar verir).
    """

    def find_email_snapshot(self, user_id: UserId) -> str | None: ...
