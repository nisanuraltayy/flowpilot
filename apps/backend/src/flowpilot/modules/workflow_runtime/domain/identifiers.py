"""Workflow Runtime public identifier value object'leri (PRD §34.1 — UUID/ULID).

Saf domain primitive'leri; hiçbir framework/ORM import etmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class WorkflowDefinitionId:
    """Mantıksal workflow (süreç ailesi) kimliği."""

    value: UUID


@dataclass(frozen=True, slots=True)
class WorkflowDefinitionVersionId:
    """Yayınlanmış, immutable bir workflow version'ının kimliği."""

    value: UUID


@dataclass(frozen=True, slots=True)
class WorkflowInstanceId:
    """Bir workflow version'ının tek çalışmasının kimliği."""

    value: UUID


@dataclass(frozen=True, slots=True)
class WorkflowTaskId:
    """Bir human task'ın (ör. onay adımı) kimliği."""

    value: UUID


@dataclass(frozen=True, slots=True)
class WorkflowEventId:
    """Bir runtime event'inin (timeline/outbox) kimliği."""

    value: UUID


@dataclass(frozen=True, slots=True)
class TimerId:
    """Persisted bir timer'ın kimliği."""

    value: UUID
