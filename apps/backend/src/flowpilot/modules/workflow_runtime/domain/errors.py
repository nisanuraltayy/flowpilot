"""Workflow Runtime domain error'ları.

Hepsi `DomainError`'dan türer; stabil, yakalanabilir tipler (PRD §38.15). Bir
hata "crash" değil, kontrollü bir domain sonucudur — application katmanı bunları
HTTP/audit sonuçlarına eşler.
"""

from __future__ import annotations

from flowpilot.shared.errors import DomainError


class WorkflowRuntimeError(DomainError):
    """Tüm workflow runtime domain hatalarının tabanı."""


class DefinitionValidationError(WorkflowRuntimeError):
    """Workflow definition yayınlanamaz (geçersiz graf, bilinmeyen node, vb.)."""


class ImmutableVersionError(WorkflowRuntimeError):
    """Yayınlanmış version değiştirilemez (immutable)."""


class ConditionEvaluationError(WorkflowRuntimeError):
    """Condition girdisi geçersiz (eksik alan, yanlış tip, para birimi uyuşmazlığı)."""


class SequenceOrderError(WorkflowRuntimeError):
    """Sıralı onayda henüz aktif olmayan adıma karar verilmeye çalışıldı."""


class UnauthorizedApproverError(WorkflowRuntimeError):
    """Actor, task'ın atandığı rolde değil."""


class DuplicateDecisionError(WorkflowRuntimeError):
    """Task için zaten terminal karar var; farklı komut conflict alır."""


class ConcurrencyConflictError(WorkflowRuntimeError):
    """Optimistic concurrency conflict — stale write reddedildi (409/412)."""


class TerminalInstanceError(WorkflowRuntimeError):
    """Terminal instance hiçbir yoldan ilerletilemez (domain-boundaries §4/5)."""


class InvalidTransitionError(WorkflowRuntimeError):
    """State machine'de tanımsız/geçersiz geçiş."""


class WorkflowInstanceNotFoundError(WorkflowRuntimeError):
    """Instance yok VEYA erişim yok — varlık bilgisi sızdırılmaz (404 semantiği)."""


class WorkflowTaskNotFoundError(WorkflowRuntimeError):
    """Task yok VEYA erişim yok — varlık bilgisi sızdırılmaz."""


class DefinitionVersionNotFoundError(WorkflowRuntimeError):
    """Published version yok VEYA erişim yok."""


class SelfApprovalForbiddenError(WorkflowRuntimeError):
    """Talep sahibi kendi talebindeki onay adımını sonuçlandıramaz (FP-E06-009).

    Karar anı savunması (defense-in-depth): assignee snapshot'ı yanlışlıkla requester
    olsa (legacy/veri uyumsuzluğu) veya doğrudan API çağrısı yapılsa bile reddedilir.
    """


class TaskNotBlockedError(WorkflowRuntimeError):
    """Resolve yalnız self-approval nedeniyle blocked kalan adım için geçerlidir."""
