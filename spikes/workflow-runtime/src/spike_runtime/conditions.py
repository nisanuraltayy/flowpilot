"""Güvenli, deterministik condition evaluator.

- `eval`/`exec`/template engine YOK — koşullar saf veri olarak yorumlanır.
- Operatör seti whitelist'tir; bilinmeyen operatör kontrollü hata üretir.
- Tutarlar minor unit (int) + ISO-4217 currency olarak karşılaştırılır; float YOK.
- Aynı girdi her zaman aynı çıktıyı üretir ve sonuç AÇIKLANABİLİRDİR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from spike_runtime.errors import ConditionEvaluationError, PublishValidationError

ALLOWED_OPS: frozenset[str] = frozenset({"lt", "lte", "gt", "gte", "eq", "otherwise"})
MAX_BRANCHES = 16  # maksimum expression karmaşıklığı (spike sınırı)

_OP_LABEL = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">=", "eq": "=="}


@dataclass(frozen=True)
class BranchResult:
    branch_id: str
    next_node: str
    explanation: str


def validate_branches(branches: list[dict[str, Any]]) -> None:
    """Publish sırasında koşul yapısını doğrular (çalıştırma yok, yalnız şema)."""
    if not branches:
        raise PublishValidationError("condition node en az bir branch içermelidir")
    if len(branches) > MAX_BRANCHES:
        raise PublishValidationError("branch sayısı sınırı aşıldı")
    for i, branch in enumerate(branches):
        when = branch.get("when")
        if not isinstance(when, dict):
            raise PublishValidationError(f"branch[{i}] 'when' nesnesi eksik")
        op = when.get("op")
        if op not in ALLOWED_OPS:
            raise PublishValidationError(f"branch[{i}] bilinmeyen operatör: {op!r}")
        if op == "otherwise":
            if i != len(branches) - 1:
                raise PublishValidationError("'otherwise' yalnız son branch olabilir")
            continue
        if not isinstance(when.get("field"), str):
            raise PublishValidationError(f"branch[{i}] 'field' string olmalı")
        if not isinstance(when.get("value"), int) or isinstance(when.get("value"), bool):
            raise PublishValidationError(f"branch[{i}] 'value' tam sayı (minor unit) olmalı")
        if not isinstance(when.get("currency"), str):
            raise PublishValidationError(f"branch[{i}] 'currency' zorunlu")
        if not isinstance(branch.get("next"), str):
            raise PublishValidationError(f"branch[{i}] 'next' hedef node'u eksik")


def evaluate(branches: list[dict[str, Any]], context: dict[str, Any]) -> BranchResult:
    """İlk eşleşen branch'i döndürür. Eksik/yanlış tip girdi → kontrollü hata.

    Girdi hiçbir koşulda kod olarak yorumlanmaz; string payload'lar
    (örn. ``__import__('os')...``) yalnız tip hatası üretir, ASLA çalıştırılmaz.
    """
    for branch in branches:
        when = branch["when"]
        op = str(when["op"])
        branch_id = str(branch.get("branch_id", "?"))
        next_node = str(branch["next"])
        if op == "otherwise":
            return BranchResult(branch_id, next_node, "hiçbir önceki koşul eşleşmedi (otherwise)")

        field = str(when["field"])
        expected_currency = str(when["currency"])
        threshold = when["value"]
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
        matched = _compare(op, actual, int(threshold))
        if matched:
            explanation = (
                f"{field}={actual} minor unit {expected_currency} "
                f"{_OP_LABEL[op]} {threshold} → branch '{branch_id}'"
            )
            return BranchResult(branch_id, next_node, explanation)
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
