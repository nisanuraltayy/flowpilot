"""Güvenli, deterministik, açıklanabilir condition evaluator (PRD §36.1, FF-08).

- `eval`/`exec`/template engine YOK — koşullar saf veri olarak yorumlanır.
- Operatör whitelist'i; bilinmeyen operatör kontrollü hata üretir.
- Tutarlar minor unit (int) + ISO-4217 currency; float YASAK.
- Aynı girdi → aynı çıktı; sonuç açıklanabilir ("tutar 50.000 TL'den büyük...").
- Eşikler burada DEĞİL, workflow definition'ın Condition node'undadır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flowpilot.modules.workflow_runtime.domain.errors import (
    ConditionEvaluationError,
    DefinitionValidationError,
)

ALLOWED_OPS: frozenset[str] = frozenset({"lt", "lte", "gt", "gte", "eq", "otherwise"})
MAX_BRANCHES = 16

_OP_LABEL = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">=", "eq": "=="}


@dataclass(frozen=True, slots=True)
class BranchSelection:
    """Bir condition değerlendirmesinin açıklanabilir sonucu."""

    branch_id: str
    next_node_id: str
    explanation: str


def validate_branches(branches: list[dict[str, Any]]) -> None:
    """Publish sırasında koşul YAPISINI doğrular (çalıştırma yok, yalnız şema)."""
    if not branches:
        raise DefinitionValidationError("condition node en az bir branch içermelidir")
    if len(branches) > MAX_BRANCHES:
        raise DefinitionValidationError("branch sayısı sınırı aşıldı")
    for index, branch in enumerate(branches):
        when = branch.get("when")
        if not isinstance(when, dict):
            raise DefinitionValidationError(f"branch[{index}] 'when' nesnesi eksik")
        op = when.get("op")
        if op not in ALLOWED_OPS:
            raise DefinitionValidationError(f"branch[{index}] bilinmeyen operatör: {op!r}")
        if not isinstance(branch.get("branch_id"), str):
            raise DefinitionValidationError(f"branch[{index}] 'branch_id' zorunlu")
        if not isinstance(branch.get("next"), str):
            raise DefinitionValidationError(f"branch[{index}] 'next' hedef node'u eksik")
        if op == "otherwise":
            if index != len(branches) - 1:
                raise DefinitionValidationError("'otherwise' yalnız SON branch olabilir")
            continue
        if not isinstance(when.get("field"), str):
            raise DefinitionValidationError(f"branch[{index}] 'field' string olmalı")
        value = when.get("value")
        if not isinstance(value, int) or isinstance(value, bool):
            raise DefinitionValidationError(
                f"branch[{index}] 'value' tam sayı (minor unit) olmalı; float YASAK"
            )
        if not isinstance(when.get("currency"), str):
            raise DefinitionValidationError(f"branch[{index}] 'currency' zorunlu")
    if branches[-1]["when"]["op"] != "otherwise":
        raise DefinitionValidationError(
            "condition node deterministik olmalı: son branch 'otherwise' olmalıdır"
        )


def evaluate(branches: list[dict[str, Any]], context: dict[str, Any]) -> BranchSelection:
    """İlk eşleşen branch'i döndürür. Girdi ASLA kod olarak yorumlanmaz.

    String payload'lar (ör. ``__import__('os')...``) yalnız tip hatası üretir.
    """
    for branch in branches:
        when = branch["when"]
        op = str(when["op"])
        branch_id = str(branch["branch_id"])
        next_node = str(branch["next"])
        if op == "otherwise":
            return BranchSelection(
                branch_id, next_node, "hiçbir önceki koşul eşleşmedi (otherwise)"
            )

        field = str(when["field"])
        expected_currency = str(when["currency"])
        threshold = int(when["value"])
        if field not in context:
            raise ConditionEvaluationError(f"koşul alanı eksik: {field!r}")
        actual = context[field]
        if actual is None:
            raise ConditionEvaluationError(f"koşul alanı null: {field!r}")
        if not isinstance(actual, int) or isinstance(actual, bool):
            raise ConditionEvaluationError(
                f"koşul alanı {field!r} tam sayı (minor unit) olmalı; "
                f"{type(actual).__name__} reddedildi"
            )
        actual_currency = context.get("currency")
        if actual_currency != expected_currency:
            raise ConditionEvaluationError(
                f"para birimi uyuşmazlığı: beklenen {expected_currency!r}, "
                f"gelen {actual_currency!r} — farklı para birimleri karşılaştırılamaz"
            )
        if _compare(op, actual, threshold):
            explanation = (
                f"{field}={actual} minor unit {expected_currency} "
                f"{_OP_LABEL[op]} {threshold} → branch '{branch_id}'"
            )
            return BranchSelection(branch_id, next_node, explanation)
    # validate_branches 'otherwise' zorunlu kıldığı için buraya normalde ulaşılmaz.
    raise ConditionEvaluationError("hiçbir branch eşleşmedi ve 'otherwise' yok")


def _compare(op: str, left: int, right: int) -> bool:
    if op == "lt":
        return left < right
    if op == "lte":
        return left <= right
    if op == "gt":
        return left > right
    if op == "gte":
        return left >= right
    if op == "eq":
        return left == right
    raise ConditionEvaluationError(f"bilinmeyen operatör: {op!r}")
