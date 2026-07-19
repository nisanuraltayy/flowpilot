"""SPK-03 (unit): güvenli, deterministik, açıklanabilir condition evaluator."""

from __future__ import annotations

from typing import Any

import pytest

from spike_runtime.conditions import evaluate, validate_branches
from spike_runtime.definition import load_fixture, node_by_id
from spike_runtime.errors import ConditionEvaluationError, PublishValidationError


def _branches() -> list[dict[str, Any]]:
    definition = load_fixture("purchase_request_v1.json")
    node = node_by_id(definition, "amount_condition")
    return list(node["config"]["branches"])


def _ctx(amount: Any, currency: Any = "TRY") -> dict[str, Any]:
    return {"amount_minor": amount, "currency": currency}


class TestBoundaryValues:
    """Sınır değerleri: 10.000 TL = 1_000_000 kuruş, 50.000 TL = 5_000_000 kuruş.

    mvp-scope §6: <10.000 → 1 adım; 10.000–50.000 → 2 adım; >50.000 → 3 adım.
    """

    @pytest.mark.parametrize(
        ("amount_minor", "expected_branch", "expected_next"),
        [
            (999_999, "low", "approval_low"),  # 9.999,99 TL
            (1_000_000, "mid", "approval_mid"),  # tam 10.000,00 TL → 2 adım
            (1_000_001, "mid", "approval_mid"),  # 10.000,01 TL
            (4_999_999, "mid", "approval_mid"),
            (5_000_000, "mid", "approval_mid"),  # tam 50.000 TL → hâlâ 2 adım
            (5_000_001, "high", "approval_high"),  # 50.000,01 TL → 3 adım
            (1, "low", "approval_low"),
        ],
    )
    def test_correct_branch(
        self, amount_minor: int, expected_branch: str, expected_next: str
    ) -> None:
        result = evaluate(_branches(), _ctx(amount_minor))
        assert result.branch_id == expected_branch
        assert result.next_node == expected_next


class TestControlledErrors:
    def test_missing_field(self) -> None:
        with pytest.raises(ConditionEvaluationError, match="eksik"):
            evaluate(_branches(), {"currency": "TRY"})

    def test_null_amount(self) -> None:
        with pytest.raises(ConditionEvaluationError, match="null"):
            evaluate(_branches(), _ctx(None))

    def test_string_amount_rejected(self) -> None:
        with pytest.raises(ConditionEvaluationError, match="tam sayı"):
            evaluate(_branches(), _ctx("1000000"))

    def test_bool_amount_rejected(self) -> None:
        with pytest.raises(ConditionEvaluationError, match="tam sayı"):
            evaluate(_branches(), _ctx(True))

    def test_currency_mismatch_rejected(self) -> None:
        # Farklı para birimleri karşılaştırılamaz — sessiz dönüşüm YOK.
        with pytest.raises(ConditionEvaluationError, match="para birimi"):
            evaluate(_branches(), _ctx(1_000_000, "USD"))

    def test_malicious_payload_never_executed(self, tmp_path: Any) -> None:
        """Zararlı ifade string'i kod olarak ÇALIŞTIRILMAZ; tip hatasıyla reddedilir."""
        canary = tmp_path / "pwned.txt"
        payload = f"__import__('pathlib').Path(r'{canary}').write_text('pwn')"
        with pytest.raises(ConditionEvaluationError, match="tam sayı"):
            evaluate(_branches(), _ctx(payload))
        assert not canary.exists(), "payload çalıştırıldı — GÜVENLİK İHLALİ"


class TestDeterminismAndExplainability:
    def test_same_input_same_output(self) -> None:
        results = {
            (r.branch_id, r.next_node, r.explanation)
            for r in (evaluate(_branches(), _ctx(1_000_000)) for _ in range(200))
        }
        assert len(results) == 1

    def test_explanation_is_meaningful(self) -> None:
        result = evaluate(_branches(), _ctx(5_000_001))
        # 'otherwise' dalı: önceki koşulların eşleşmediği açıkça söylenir.
        assert "otherwise" in result.explanation
        mid = evaluate(_branches(), _ctx(2_500_000))
        assert "amount_minor=2500000" in mid.explanation
        assert "TRY" in mid.explanation
        assert "<= 5000000" in mid.explanation


class TestPublishTimeValidation:
    def test_unknown_operator_rejected(self) -> None:
        with pytest.raises(PublishValidationError, match="bilinmeyen operatör"):
            validate_branches(
                [{"when": {"op": "regex", "field": "x", "value": 1, "currency": "TRY"}}]
            )

    def test_otherwise_must_be_last(self) -> None:
        with pytest.raises(PublishValidationError, match="son branch"):
            validate_branches(
                [
                    {"when": {"op": "otherwise"}, "next": "a"},
                    {
                        "when": {"op": "lt", "field": "x", "value": 1, "currency": "TRY"},
                        "next": "b",
                    },
                ]
            )

    def test_float_threshold_rejected(self) -> None:
        # Para float olamaz — eşik minor unit tam sayısı olmak zorunda.
        with pytest.raises(PublishValidationError, match="tam sayı"):
            validate_branches(
                [
                    {
                        "when": {"op": "lt", "field": "x", "value": 10000.5, "currency": "TRY"},
                        "next": "a",
                    }
                ]
            )

    def test_max_branch_complexity(self) -> None:
        too_many = [
            {"when": {"op": "lt", "field": "x", "value": i, "currency": "TRY"}, "next": "a"}
            for i in range(17)
        ]
        with pytest.raises(PublishValidationError, match="sınırı"):
            validate_branches(too_many)
