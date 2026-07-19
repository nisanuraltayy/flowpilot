"""Spike domain hataları — hepsi kontrollü, crash değil."""

from __future__ import annotations


class SpikeError(Exception):
    """Tüm spike domain hatalarının tabanı."""


class PublishValidationError(SpikeError):
    """Definition yayınlanamaz (bilinmeyen node tipi, kopuk graf, geçersiz koşul)."""


class ImmutableVersionError(SpikeError):
    """Published version değiştirilemez."""


class ConditionEvaluationError(SpikeError):
    """Koşul girdisi geçersiz (eksik alan, yanlış tip, para birimi uyuşmazlığı)."""


class NotFoundError(SpikeError):
    """Kaynak yok VEYA erişim yok — varlık bilgisi sızdırılmaz (404 semantiği)."""


class UnauthorizedApproverError(SpikeError):
    """Actor, step'in atandığı rolde değil (403 benzeri; audit'e yazılır)."""


class SequenceOrderError(SpikeError):
    """Sıralı onayda henüz aktif olmayan step'e karar verilmeye çalışıldı (403 benzeri)."""


class DuplicateDecisionError(SpikeError):
    """Step için zaten terminal karar var; farklı bir komut conflict alır (409 benzeri)."""


class StaleVersionError(SpikeError):
    """Optimistic concurrency conflict (409/412 benzeri). Sessiz üzerine yazma YOK."""


class TerminalInstanceError(SpikeError):
    """Terminal instance hiçbir yoldan ilerletilemez (PRD §36.1/5)."""


class InvalidTransitionError(SpikeError):
    """State machine'de tanımsız geçiş kontrollü reddedilir."""
