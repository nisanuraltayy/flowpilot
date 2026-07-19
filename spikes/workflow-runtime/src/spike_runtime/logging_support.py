"""Correlation alanlı, JSON satırlı spike loglaması.

Zorunlu correlation alanları: tenant_id, workflow_instance_id,
workflow_definition_version, task_id, event_id, transition, attempt.
Token/secret/kişisel veri LOGLANMAZ (bu alanlar zaten spike'ta yoktur).
"""

from __future__ import annotations

import json
import logging
from typing import Any

_LOGGER = logging.getLogger("spike_runtime")

CORRELATION_FIELDS = (
    "tenant_id",
    "workflow_instance_id",
    "workflow_definition_version",
    "task_id",
    "event_id",
    "transition",
    "attempt",
)


def log_event(action: str, **fields: Any) -> None:
    record: dict[str, Any] = {"action": action}
    for key in CORRELATION_FIELDS:
        record[key] = str(fields[key]) if fields.get(key) is not None else None
    for key, value in fields.items():
        if key not in CORRELATION_FIELDS:
            record[key] = str(value)
    _LOGGER.info(json.dumps(record, ensure_ascii=False, sort_keys=True))
