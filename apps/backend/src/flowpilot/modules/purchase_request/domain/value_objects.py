"""Purchase Request başlık/açıklama value object'leri.

Üst sınırlar bilinçli seçildi ve gerekçelendirildi:
- Başlık 200 karakter: organization adıyla (200) tutarlı; tek satırlık özet için yeterli.
- Açıklama 2000 karakter: kısa gerekçe/serbest metin; DoS/aşırı payload'a karşı sınır.
Sunucu tarafı doğrulama zorunludur (UI doğrulaması bypass edilebilir kabul edilir).
"""

from __future__ import annotations

from dataclasses import dataclass

from flowpilot.modules.purchase_request.domain.errors import (
    InvalidDescriptionError,
    InvalidTitleError,
)

TITLE_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 2000


@dataclass(frozen=True, slots=True)
class PurchaseRequestTitle:
    """Boş/whitespace olamaz; 1-200 karakter (kenar boşlukları kırpılır)."""

    value: str

    def __init__(self, raw: str) -> None:
        trimmed = raw.strip()
        if not trimmed:
            raise InvalidTitleError("başlık boş veya yalnızca boşluk olamaz")
        if len(trimmed) > TITLE_MAX_LENGTH:
            raise InvalidTitleError(f"başlık en çok {TITLE_MAX_LENGTH} karakter olabilir")
        object.__setattr__(self, "value", trimmed)


@dataclass(frozen=True, slots=True)
class PurchaseRequestDescription:
    """Opsiyonel; verilirse en çok 2000 karakter."""

    value: str | None

    def __init__(self, raw: str | None) -> None:
        if raw is None:
            object.__setattr__(self, "value", None)
            return
        trimmed = raw.strip()
        if not trimmed:
            object.__setattr__(self, "value", None)
            return
        if len(trimmed) > DESCRIPTION_MAX_LENGTH:
            raise InvalidDescriptionError(
                f"açıklama en çok {DESCRIPTION_MAX_LENGTH} karakter olabilir"
            )
        object.__setattr__(self, "value", trimmed)
