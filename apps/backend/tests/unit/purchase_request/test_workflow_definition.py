"""Varsayılan Purchase Request workflow definition: validation, hash, threshold branch."""

from __future__ import annotations

import pytest

from flowpilot.modules.purchase_request.application.workflow import (
    WORKFLOW_KEY,
    load_default_definition,
)
from flowpilot.modules.workflow_runtime.domain.conditions import evaluate
from flowpilot.modules.workflow_runtime.domain.definition import (
    canonical_hash,
    validate_definition,
)


def test_definition_passes_runtime_validation() -> None:
    validate_definition(load_default_definition())


def test_definition_key_matches() -> None:
    assert load_default_definition()["workflow_key"] == WORKFLOW_KEY


def test_canonical_hash_is_deterministic() -> None:
    d1 = load_default_definition()
    d2 = load_default_definition()
    assert canonical_hash(d1) == canonical_hash(d2)


def _branches() -> list[dict[str, object]]:
    definition = load_default_definition()
    node = next(n for n in definition["nodes"] if n["type"] == "condition")
    return list(node["config"]["branches"])


@pytest.mark.parametrize(
    ("amount_minor", "expected_next"),
    [
        (999_999, "approval_team_manager"),  # 9.999,99 TL
        (1_000_000, "approval_team_manager_finance"),  # 10.000,00 TL
        (5_000_000, "approval_team_manager_finance"),  # 50.000,00 TL
        (5_000_001, "approval_full_chain"),  # 50.000,01 TL
    ],
)
def test_threshold_boundaries(amount_minor: int, expected_next: str) -> None:
    result = evaluate(_branches(), {"amount_minor": amount_minor, "currency": "TRY"})
    assert result.next_node_id == expected_next


def test_no_threshold_hardcoded_in_module_python() -> None:
    """Eşikler yalnız JSON resource'ta; modül .py kodunda 1000000/5000000 GEÇMEZ."""
    import pathlib

    import flowpilot.modules.purchase_request as pkg

    root = pathlib.Path(pkg.__file__).parent
    for py in root.rglob("*.py"):
        source = py.read_text(encoding="utf-8")
        assert "1000000" not in source and "5000000" not in source, (
            f"onay eşiği koda hard-code edilmiş: {py}"
        )
