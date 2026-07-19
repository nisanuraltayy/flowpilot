"""Workflow definition yükleme, doğrulama ve içerik hash'i.

- MVP node whitelist'i dışındaki tip YAYINLANAMAZ (FF-16 analog).
- Hash = canonical JSON'un SHA-256'sı; publish sonrası bit düzeyinde sabit kalmalıdır.
- Onay eşikleri ve zincirler BU definition'dadır — Python koduna hard-code edilmez.
"""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from typing import Any, cast

from spike_runtime.conditions import validate_branches
from spike_runtime.errors import PublishValidationError

ALLOWED_NODE_TYPES: frozenset[str] = frozenset(
    {"start", "form", "condition", "sequential_approval", "notification", "end"}
)


def load_fixture(name: str) -> dict[str, Any]:
    raw = resources.files("spike_runtime.fixtures").joinpath(name).read_text(encoding="utf-8")
    return cast(dict[str, Any], json.loads(raw))


def content_hash(definition: dict[str, Any]) -> str:
    canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def node_by_id(definition: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in definition["nodes"]:
        if node["id"] == node_id:
            return cast(dict[str, Any], node)
    raise PublishValidationError(f"node bulunamadı: {node_id!r}")


def validate_definition(definition: dict[str, Any]) -> None:
    nodes = definition.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise PublishValidationError("definition en az bir node içermelidir")

    ids: set[str] = set()
    start_count = 0
    for node in nodes:
        node_type = node.get("type")
        if node_type not in ALLOWED_NODE_TYPES:
            raise PublishValidationError(
                f"bilinmeyen node tipi yayınlanamaz: {node_type!r} "
                f"(izin verilen: {sorted(ALLOWED_NODE_TYPES)})"
            )
        node_id = node.get("id")
        if not isinstance(node_id, str) or node_id in ids:
            raise PublishValidationError(f"geçersiz/tekrarlı node id: {node_id!r}")
        ids.add(node_id)
        if node_type == "start":
            start_count += 1
        if node_type == "condition":
            validate_branches(list(node.get("config", {}).get("branches", [])))
        if node_type == "sequential_approval":
            chain = node.get("config", {}).get("approver_chain")
            if not isinstance(chain, list) or not chain or len(chain) > 3:
                raise PublishValidationError(
                    "sequential_approval 1-3 adımlı approver_chain gerektirir"
                )
    if start_count != 1:
        raise PublishValidationError("tam olarak bir start node gerekir")

    # Kenar bütünlüğü: her 'next' referansı var olan bir node'a işaret etmeli.
    for node in nodes:
        targets: list[str] = []
        if isinstance(node.get("next"), str):
            targets.append(node["next"])
        for branch in node.get("config", {}).get("branches", []):
            targets.append(branch["next"])
        for target in targets:
            if target not in ids:
                raise PublishValidationError(f"kopuk kenar: {node['id']!r} → {target!r}")
