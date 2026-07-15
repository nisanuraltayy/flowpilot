"""ID üretimi port'u — domain içinde doğrudan random ID üretmek YASAK.

Injectable generator sayesinde testler deterministik ID kullanabilir.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4


class IdGeneratorPort(Protocol):
    """Yeni public identifier üreten port."""

    def new_uuid(self) -> UUID: ...


class UuidGenerator:
    """Rastgele UUID4 üretir."""

    def new_uuid(self) -> UUID:
        return uuid4()
