"""Session/tenant-context yardımcıları.

Tenant scope PostgreSQL transaction-local ayar ile taşınır (`set_config(..., true)`):
transaction bitince otomatik sıfırlanır, bağlantı havuzuna sızmaz. Boş/eksik context
RLS policy'lerinde güvenli RED üretir (metin karşılaştırması, hata değil).
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, Result, text
from sqlalchemy.orm import Session


def rowcount(result: Result[Any]) -> int:
    """DML sonucu etkilenen satır sayısı (mypy-strict dostu erişim)."""
    return int(cast(CursorResult[Any], result).rowcount)


def set_tenant_context(session: Session, tenant_id: UUID) -> None:
    session.execute(
        text("SELECT set_config('app.current_tenant_id', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


def set_actor_context(session: Session, actor_id: str) -> None:
    session.execute(
        text("SELECT set_config('app.current_actor_id', :actor, true)"),
        {"actor": actor_id},
    )
