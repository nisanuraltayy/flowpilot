"""Purchase Request public identifier'ı (PRD §34.1 — UUID/ULID)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PurchaseRequestId:
    """Bir satın alma talebinin değişmez kimliği."""

    value: UUID
