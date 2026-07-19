"""Varsayılan Purchase Request workflow definition'ının stable key + yükleyicisi.

Definition Python içinde if/else olarak DEĞİL, versioned bir JSON package resource
olarak tutulur. Onay eşikleri bu resource'un Condition node'undadır.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, cast

WORKFLOW_KEY = "purchase_request_approval"
WORKFLOW_VERSION_NO = 1
_RESOURCE = "purchase_request_approval_v1.json"


def load_default_definition() -> dict[str, Any]:
    """Varsayılan definition JSON'unu package resource'undan yükler."""
    raw = (
        resources.files("flowpilot.modules.purchase_request.application.resources")
        .joinpath(_RESOURCE)
        .read_text(encoding="utf-8")
    )
    return cast(dict[str, Any], json.loads(raw))
