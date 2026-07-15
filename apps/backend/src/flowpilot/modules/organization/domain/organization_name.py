"""OrganizationName value object'i ve doğrulaması.

Kurallar:
- Boş olamaz, yalnız boşluk olamaz.
- En fazla 200 karakter. Gerekçe: bu bir GÖSTERİM adıdır; 200, gerçek herhangi
  bir organizasyon adı için fazlasıyla yeterlidir ve depolama/DoS için üst
  sınır sağlar. DB kolonu da VARCHAR(200)'dür.
- Değer normalize edilir (baş/son boşluk kırpılır) ve immutable saklanır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from flowpilot.modules.organization.domain.errors import (
    EmptyOrganizationNameError,
    OrganizationNameTooLongError,
)


@dataclass(frozen=True)
class OrganizationName:
    """Doğrulanmış organizasyon adı."""

    MAX_LENGTH: ClassVar[int] = 200

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not normalized:
            raise EmptyOrganizationNameError()
        if len(normalized) > self.MAX_LENGTH:
            raise OrganizationNameTooLongError(self.MAX_LENGTH)
        # frozen dataclass — normalize edilmiş değeri yaz.
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
