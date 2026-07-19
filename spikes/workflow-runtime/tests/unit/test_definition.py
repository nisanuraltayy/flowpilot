"""Definition doğrulama + içerik hash'i (SPK-01 destek kanıtı, FF-16 analog)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from spike_runtime.definition import content_hash, load_fixture, validate_definition
from spike_runtime.errors import PublishValidationError


def test_fixture_v1_and_v2_are_valid() -> None:
    validate_definition(load_fixture("purchase_request_v1.json"))
    validate_definition(load_fixture("purchase_request_v2.json"))


def test_hash_is_deterministic_and_key_order_insensitive() -> None:
    definition = load_fixture("purchase_request_v1.json")
    reordered = {k: definition[k] for k in sorted(definition, reverse=True)}
    assert content_hash(definition) == content_hash(reordered)
    assert content_hash(definition) == content_hash(copy.deepcopy(definition))


def test_hash_changes_when_threshold_changes() -> None:
    definition = load_fixture("purchase_request_v1.json")
    mutated = copy.deepcopy(definition)
    mutated["nodes"][2]["config"]["branches"][0]["when"]["value"] = 999
    assert content_hash(definition) != content_hash(mutated)


@pytest.mark.parametrize(
    "bad_type", ["script", "webhook", "ai", "dmn", "parallel_split", "sub_workflow"]
)
def test_non_mvp_node_types_cannot_publish(bad_type: str) -> None:
    definition: dict[str, Any] = load_fixture("purchase_request_v1.json")
    definition["nodes"].append({"id": "evil", "type": bad_type})
    with pytest.raises(PublishValidationError, match="bilinmeyen node tipi"):
        validate_definition(definition)


def test_chain_longer_than_three_rejected() -> None:
    definition = load_fixture("purchase_request_v1.json")
    definition["nodes"][3]["config"]["approver_chain"] = ["a", "b", "c", "d"]
    with pytest.raises(PublishValidationError, match="1-3 adım"):
        validate_definition(definition)


def test_broken_edge_rejected() -> None:
    definition = load_fixture("purchase_request_v1.json")
    definition["nodes"][0]["next"] = "yok-boyle-node"
    with pytest.raises(PublishValidationError, match="kopuk kenar"):
        validate_definition(definition)


def test_thresholds_live_in_definition_not_in_code() -> None:
    """Eşikler (1_000_000 / 5_000_000 kuruş) yalnız fixture'dadır — kodda DEĞİL."""
    import spike_runtime

    src_dir = __import__("pathlib").Path(spike_runtime.__file__).parent
    for py in src_dir.glob("*.py"):
        source = py.read_text(encoding="utf-8")
        assert "1000000" not in source and "5000000" not in source, (
            f"onay eşiği koda hard-code edilmiş: {py.name}"
        )
