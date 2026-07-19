"""WorkflowDefinitionVersion — yayınlanmış, immutable workflow tanımı.

Definition JSON biçiminde saklanır ancak YAYINLANMADAN ÖNCE typed doğrulamadan
geçer. Kanıtlanan invariant'lar (spike SPK-01/SPK-02/SPK-03):
- Node ID'leri unique; tam bir Start; en az bir End.
- Bilinmeyen node tipi reddedilir (MVP node seti dışı YASAK).
- Referans verilen 'next' node mevcut olmalı; ulaşılamayan node reddedilir.
- Condition branch'leri açık ve deterministik ('otherwise' zorunlu).
- Sequential Approval adım sırası deterministik (approver_chain sırası).
- content_hash canonical JSON'dan üretilir; version immutable'dır.
- Tutar eşikleri koda hard-code edilmez; Condition node config'inden gelir.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass
from typing import Any, cast

from flowpilot.modules.workflow_runtime.domain.conditions import validate_branches
from flowpilot.modules.workflow_runtime.domain.enums import WorkflowNodeType
from flowpilot.modules.workflow_runtime.domain.errors import DefinitionValidationError
from flowpilot.modules.workflow_runtime.domain.identifiers import (
    WorkflowDefinitionId,
    WorkflowDefinitionVersionId,
)

MAX_APPROVAL_STEPS = 3  # mvp-scope §6: Sequential Approval 1-3 adımlı zincirleri destekler.


def canonical_hash(definition: dict[str, Any]) -> str:
    """Definition içeriğinin deterministik SHA-256'sı (anahtar sırası bağımsız)."""
    canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _node_targets(node: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    nxt = node.get("next")
    if isinstance(nxt, str):
        targets.append(nxt)
    for branch in node.get("config", {}).get("branches", []):
        target = branch.get("next")
        if isinstance(target, str):
            targets.append(target)
    return targets


def validate_definition(definition: dict[str, Any]) -> None:
    """Definition'ı yayınlanabilirlik açısından doğrular; ihlalde domain hatası verir."""
    nodes = definition.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise DefinitionValidationError("definition en az bir node içermelidir")

    ids: set[str] = set()
    start_ids: list[str] = []
    end_ids: list[str] = []
    for node in nodes:
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise DefinitionValidationError(f"geçersiz node id: {node_id!r}")
        if node_id in ids:
            raise DefinitionValidationError(f"tekrarlı node id: {node_id!r}")
        ids.add(node_id)

        node_type = node.get("type")
        try:
            resolved = WorkflowNodeType(node_type)
        except ValueError as exc:
            allowed = sorted(t.value for t in WorkflowNodeType)
            raise DefinitionValidationError(
                f"bilinmeyen node tipi yayınlanamaz: {node_type!r} (izin verilen: {allowed})"
            ) from exc

        if resolved is WorkflowNodeType.START:
            start_ids.append(node_id)
        elif resolved is WorkflowNodeType.END:
            end_ids.append(node_id)
        elif resolved is WorkflowNodeType.CONDITION:
            validate_branches(list(node.get("config", {}).get("branches", [])))
        elif resolved is WorkflowNodeType.SEQUENTIAL_APPROVAL:
            chain = node.get("config", {}).get("approver_chain")
            if not isinstance(chain, list) or not (1 <= len(chain) <= MAX_APPROVAL_STEPS):
                raise DefinitionValidationError(
                    f"sequential_approval 1-{MAX_APPROVAL_STEPS} adımlı approver_chain gerektirir"
                )
            if not all(isinstance(role, str) and role for role in chain):
                raise DefinitionValidationError("approver_chain adımları string rol olmalı")

    if len(start_ids) != 1:
        raise DefinitionValidationError("tam olarak bir Start node gerekir")
    if not end_ids:
        raise DefinitionValidationError("en az bir End node gerekir")

    # Kenar bütünlüğü: her 'next' var olan bir node'a işaret etmeli.
    for node in nodes:
        node_type = WorkflowNodeType(node["type"])
        targets = _node_targets(node)
        if node_type is WorkflowNodeType.END:
            if targets:
                raise DefinitionValidationError(f"End node çıkış kenarı taşıyamaz: {node['id']!r}")
            continue
        if not targets:
            raise DefinitionValidationError(f"non-terminal node çıkış kenarı yok: {node['id']!r}")
        for target in targets:
            if target not in ids:
                raise DefinitionValidationError(f"kopuk kenar: {node['id']!r} → {target!r}")

    _assert_all_reachable(nodes, start_ids[0], ids)


def _assert_all_reachable(nodes: list[dict[str, Any]], start_id: str, all_ids: set[str]) -> None:
    by_id = {node["id"]: node for node in nodes}
    seen: set[str] = set()
    queue: deque[str] = deque([start_id])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        for target in _node_targets(by_id[current]):
            if target not in seen:
                queue.append(target)
    unreachable = all_ids - seen
    if unreachable:
        raise DefinitionValidationError(
            f"ulaşılamayan node(lar) yayınlanamaz: {sorted(unreachable)}"
        )


@dataclass(frozen=True)
class WorkflowDefinitionVersion:
    """Yayınlanmış, immutable bir workflow version'ı.

    `content_hash` yayınlandığı andaki içeriğe kilitlidir; instance bu version'a
    (id + hash) sabitlenir. Domain, node tanımını instance'ın bağlı olduğu
    version'dan okur — asla "son yayınlanan"dan değil (SPK-02).
    """

    id: WorkflowDefinitionVersionId
    definition_id: WorkflowDefinitionId
    version_no: int
    definition: dict[str, Any]
    content_hash: str

    @classmethod
    def publish(
        cls,
        *,
        id: WorkflowDefinitionVersionId,
        definition_id: WorkflowDefinitionId,
        version_no: int,
        definition: dict[str, Any],
    ) -> WorkflowDefinitionVersion:
        """Doğrulanmış, hash'lenmiş immutable bir version üretir."""
        if version_no < 1:
            raise DefinitionValidationError("version_no >= 1 olmalı")
        validate_definition(definition)
        return cls(
            id=id,
            definition_id=definition_id,
            version_no=version_no,
            definition=definition,
            content_hash=canonical_hash(definition),
        )

    def node(self, node_id: str) -> dict[str, Any]:
        for node in self.definition["nodes"]:
            if node["id"] == node_id:
                return cast(dict[str, Any], node)
        raise DefinitionValidationError(f"node bulunamadı: {node_id!r}")

    def start_node(self) -> dict[str, Any]:
        for node in self.definition["nodes"]:
            if node["type"] == WorkflowNodeType.START.value:
                return cast(dict[str, Any], node)
        raise DefinitionValidationError("start node yok")  # publish doğrulaması engeller
