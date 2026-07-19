"""workflow_runtime'ın DIŞARIYA sunduğu application-level error vocabulary'si.

Başka modüller (ör. purchase_request) runtime hatalarını YALNIZ bu application
sınırından yakalar — workflow_runtime.domain'i doğrudan import ETMEZ
(dependency-rules §2, cross-context domain importu yasak). İçerik domain
error'larıdır; burada yalnız kontrat olarak yeniden dışa verilir.
"""

from __future__ import annotations

from flowpilot.modules.workflow_runtime.domain.errors import (
    ConcurrencyConflictError,
    DefinitionValidationError,
    DuplicateDecisionError,
    InvalidTransitionError,
    SequenceOrderError,
    TerminalInstanceError,
    UnauthorizedApproverError,
    WorkflowInstanceNotFoundError,
    WorkflowRuntimeError,
    WorkflowTaskNotFoundError,
)

__all__ = [
    "ConcurrencyConflictError",
    "DefinitionValidationError",
    "DuplicateDecisionError",
    "InvalidTransitionError",
    "SequenceOrderError",
    "TerminalInstanceError",
    "UnauthorizedApproverError",
    "WorkflowInstanceNotFoundError",
    "WorkflowRuntimeError",
    "WorkflowTaskNotFoundError",
]
