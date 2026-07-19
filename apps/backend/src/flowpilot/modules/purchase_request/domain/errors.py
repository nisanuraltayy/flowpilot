"""Purchase Request domain error'ları (hepsi kontrollü, crash değil)."""

from __future__ import annotations

from flowpilot.shared.errors import DomainError


class PurchaseRequestError(DomainError):
    """Tüm purchase request domain hatalarının tabanı."""


class InvalidMoneyError(PurchaseRequestError):
    """Tutar/para birimi geçersiz (≤0, float, desteklenmeyen currency)."""


class InvalidTitleError(PurchaseRequestError):
    """Başlık boş/whitespace veya üst sınırı aşıyor."""


class InvalidDescriptionError(PurchaseRequestError):
    """Açıklama üst sınırı aşıyor."""


class InvalidPurchaseRequestTransitionError(PurchaseRequestError):
    """Purchase request state machine'de tanımsız geçiş."""


class PurchaseRequestConcurrencyError(PurchaseRequestError):
    """Optimistic concurrency conflict — stale write reddedildi (409)."""
