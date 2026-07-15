"""Organization domain error'ları."""

from __future__ import annotations

from flowpilot.shared.errors import DomainError


class OrganizationNameError(DomainError):
    """Organization adı geçersiz."""


class EmptyOrganizationNameError(OrganizationNameError):
    """Organization adı boş veya yalnızca boşluk."""

    def __init__(self) -> None:
        super().__init__("Organizasyon adi bos olamaz.")


class OrganizationNameTooLongError(OrganizationNameError):
    """Organization adı üst sınırı aşıyor."""

    def __init__(self, max_length: int) -> None:
        super().__init__(f"Organizasyon adi en fazla {max_length} karakter olabilir.")
