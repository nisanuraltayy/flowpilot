"""Definition validation + canonical hash + published version immutability (unit)."""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
from typing import Any
from uuid import uuid4

import pytest

from flowpilot.modules.workflow_runtime.domain.definition import (
    WorkflowDefinitionVersion,
    canonical_hash,
    validate_definition,
)
from flowpilot.modules.workflow_runtime.domain.errors import DefinitionValidationError
from flowpilot.modules.workflow_runtime.domain.identifiers import (
    WorkflowDefinitionId,
    WorkflowDefinitionVersionId,
)
from tests.unit.workflow_runtime.definitions import purchase_like_v1


def _publish(definition: dict[str, Any]) -> WorkflowDefinitionVersion:
    return WorkflowDefinitionVersion.publish(
        id=WorkflowDefinitionVersionId(uuid4()),
        definition_id=WorkflowDefinitionId(uuid4()),
        version_no=1,
        definition=definition,
    )


def test_valid_definition_publishes() -> None:
    version = _publish(purchase_like_v1())
    assert version.content_hash == canonical_hash(purchase_like_v1())
    assert version.version_no == 1


def test_hash_is_key_order_insensitive() -> None:
    definition = purchase_like_v1()
    reordered = {k: definition[k] for k in sorted(definition, reverse=True)}
    assert canonical_hash(definition) == canonical_hash(reordered)


def test_hash_changes_when_threshold_changes() -> None:
    original = purchase_like_v1()
    mutated = copy.deepcopy(original)
    mutated["nodes"][2]["config"]["branches"][0]["when"]["value"] = 42
    assert canonical_hash(original) != canonical_hash(mutated)


def test_published_version_object_is_immutable() -> None:
    version = _publish(purchase_like_v1())
    with pytest.raises(FrozenInstanceError):
        version.content_hash = "tampered"  # type: ignore[misc]


def test_unique_node_ids_enforced() -> None:
    definition = purchase_like_v1()
    definition["nodes"].append({"id": "start", "type": "end"})
    with pytest.raises(DefinitionValidationError, match="tekrarlı node id"):
        validate_definition(definition)


def test_exactly_one_start() -> None:
    definition = purchase_like_v1()
    definition["nodes"].append({"id": "start2", "type": "start", "next": "end"})
    with pytest.raises(DefinitionValidationError, match="tam olarak bir Start"):
        validate_definition(definition)


def test_at_least_one_end() -> None:
    definition = purchase_like_v1()
    definition["nodes"] = [n for n in definition["nodes"] if n["type"] != "end"]
    definition["nodes"][-1]["next"] = "start"  # kenarı bağlı tut ki 'end yok' hatası çıksın
    with pytest.raises(DefinitionValidationError, match="en az bir End"):
        validate_definition(definition)


@pytest.mark.parametrize("bad_type", ["script", "webhook", "ai", "dmn", "parallel_split"])
def test_unknown_node_type_rejected(bad_type: str) -> None:
    definition = purchase_like_v1()
    definition["nodes"].append({"id": "evil", "type": bad_type})
    with pytest.raises(DefinitionValidationError, match="bilinmeyen node tipi"):
        validate_definition(definition)


def test_broken_edge_rejected() -> None:
    definition = purchase_like_v1()
    definition["nodes"][0]["next"] = "does-not-exist"
    with pytest.raises(DefinitionValidationError, match="kopuk kenar"):
        validate_definition(definition)


def test_unreachable_node_rejected() -> None:
    definition = purchase_like_v1()
    definition["nodes"].append(
        {"id": "orphan", "type": "notification", "next": "end", "config": {}}
    )
    with pytest.raises(DefinitionValidationError, match="ulaşılamayan"):
        validate_definition(definition)


def test_condition_requires_terminal_otherwise() -> None:
    definition = purchase_like_v1()
    branches = definition["nodes"][2]["config"]["branches"]
    branches[-1] = {
        "branch_id": "x",
        "when": {"field": "amount_minor", "op": "gt", "value": 1, "currency": "TRY"},
        "next": "approval_low",
    }
    with pytest.raises(DefinitionValidationError, match="otherwise"):
        validate_definition(definition)


def test_sequential_approval_chain_bounded() -> None:
    definition = purchase_like_v1()
    definition["nodes"][3]["config"]["approver_chain"] = ["a", "b", "c", "d"]
    with pytest.raises(DefinitionValidationError, match="1-3 adım"):
        validate_definition(definition)


def test_no_amount_threshold_hardcoded_in_production_domain() -> None:
    """Eşikler definition'da; production domain kodunda 1000000/5000000 GEÇMEZ."""
    import pathlib

    import flowpilot.modules.workflow_runtime as pkg

    root = pathlib.Path(pkg.__file__).parent
    for py in root.rglob("*.py"):
        source = py.read_text(encoding="utf-8")
        assert "1000000" not in source and "5000000" not in source, (
            f"onay eşiği koda hard-code edilmiş: {py}"
        )
