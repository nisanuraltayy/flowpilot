"""Fitness-check tarzı statik kanıtlar (SPK-01/SPK-03 kanıt paketi parçası).

Spike kaynak kodunda:
- `eval(` / `exec(` YOK (FF-08),
- published version tablosuna UPDATE çalıştıran SQL YOK (FF-11),
- naive `datetime.now()` / `datetime.utcnow` YOK (FF-10),
- para tipi olarak FLOAT/DOUBLE YOK (FF-09).
"""

from __future__ import annotations

import re
from pathlib import Path

import spike_runtime

SRC_DIR = Path(spike_runtime.__file__).parent
SOURCES = {p.name: p.read_text(encoding="utf-8") for p in SRC_DIR.glob("*.py")}


def test_no_eval_or_exec() -> None:
    pattern = re.compile(r"\b(eval|exec)\s*\(")
    for name, source in SOURCES.items():
        assert not pattern.search(source), f"{name} içinde eval/exec bulundu"


def test_no_update_path_to_published_versions() -> None:
    pattern = re.compile(r"UPDATE\s+spike_workflow_versions", re.IGNORECASE)
    for name, source in SOURCES.items():
        assert not pattern.search(source), (
            f"{name}: published version tablosuna UPDATE yolu bulundu (SPK-01 ihlali)"
        )


def test_no_naive_datetime() -> None:
    for name, source in SOURCES.items():
        assert "utcnow" not in source, f"{name}: datetime.utcnow (naive) yasak"
        for match in re.finditer(r"datetime\.now\(([^)]*)\)", source):
            assert match.group(1).strip(), f"{name}: tz'siz datetime.now() yasak"


def test_no_float_money_columns() -> None:
    from spike_runtime import schema

    ddl = schema._DDL.upper()  # statik kanıt testi — private erişim bilinçli
    assert "FLOAT" not in ddl and "DOUBLE" not in ddl and "REAL" not in ddl
    assert "NUMERIC" not in ddl  # tutarlar INT minor unit; para NUMERIC bile değil


def test_no_infinite_retry_constants() -> None:
    from spike_runtime.dispatcher import MAX_ATTEMPTS

    assert 1 <= MAX_ATTEMPTS <= 10, "retry bounded olmalı"
