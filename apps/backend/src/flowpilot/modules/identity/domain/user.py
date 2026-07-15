"""User — FlowPilot'ın iç kullanıcı kaydı (minimal).

Bu aşamada login, parola, session, e-posta doğrulama YOKTUR.
`external_auth_subject` ileride Supabase `sub` claim'ine bağlanacak yer tutucudur;
şimdilik None olabilir. E-posta PRIMARY KEY DEĞİLDİR (PRD §34.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from flowpilot.shared.identifiers import UserId


@dataclass(frozen=True)
class User:
    """Bir FlowPilot kullanıcısı."""

    id: UserId
    email: str
    external_auth_subject: str | None
    created_at: datetime
