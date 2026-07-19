"""Güvenli, deterministik, açıklanabilir condition evaluator (unit)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from flowpilot.modules.workflow_runtime.domain.conditions import evaluate
from flowpilot.modules.workflow_runtime.domain.errors import ConditionEvaluationError
from tests.unit.workflow_runtime.definitions import purchase_like_v1


def _branches() -> list[dict[str, Any]]:
    return list(purchase_like_v1()["nodes"][2]["config"]["branches"])


def _ctx(amount: Any, currency: Any = "TRY") -> dict[str, Any]:
    return {"amount_minor": amount, "currency": currency}


@pytest.mark.parametrize(
    ("amount", "expected_branch"),
    [
        (999_999, "low"),
        (1_000_000, "mid"),
        (1_000_001, "mid"),
        (5_000_000, "mid"),
        (5_000_001, "high"),
        (1, "low"),
    ],
)
def test_boundary_values_select_correct_branch(amount: int, expected_branch: str) -> None:
    assert evaluate(_branches(), _ctx(amount)).branch_id == expected_branch


def test_missing_field_is_controlled_error() -> None:
    with pytest.raises(ConditionEvaluationError, match="eksik"):
        evaluate(_branches(), {"currency": "TRY"})


def test_string_amount_rejected_not_executed(tmp_path: Path) -> None:
    canary = tmp_path / "pwned.txt"
    payload = f"__import__('pathlib').Path(r'{canary}').write_text('x')"
    with pytest.raises(ConditionEvaluationError, match="tam sayı"):
        evaluate(_branches(), _ctx(payload))
    assert not canary.exists(), "payload çalıştırıldı — GÜVENLİK İHLALİ"


def test_currency_mismatch_rejected() -> None:
    with pytest.raises(ConditionEvaluationError, match="para birimi"):
        evaluate(_branches(), _ctx(1_000_000, "USD"))


def test_deterministic_same_input_same_output() -> None:
    results = {
        (r.branch_id, r.explanation)
        for r in (evaluate(_branches(), _ctx(2_500_000)) for _ in range(100))
    }
    assert len(results) == 1


def test_explanation_is_meaningful() -> None:
    result = evaluate(_branches(), _ctx(2_500_000))
    assert "amount_minor=2500000" in result.explanation
    assert "TRY" in result.explanation
