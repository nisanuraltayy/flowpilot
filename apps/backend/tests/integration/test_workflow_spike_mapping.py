"""Spike 12/12 exit criterion → production regresyon eşleme raporu.

ADR-004 spike'ının kanıtladığı 12 kriterin (SPK-01..SPK-12) HER BİRİNİN production
implementasyonunda karşılık gelen bir/birden çok test ile kapsandığını doğrular.
Bir eşlenen test dosyası/fonksiyonu yoksa bu test kırmızı olur — spike kazanımları
sessizce production'da kaybolmaz.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.integration._support import REPO_ROOT

INTEGRATION_DIR = REPO_ROOT / "apps" / "backend" / "tests" / "integration"
UNIT_DIR = REPO_ROOT / "apps" / "backend" / "tests" / "unit" / "workflow_runtime"

# SPK kriteri → onu production'da kanıtlayan test fonksiyonları.
SPIKE_TO_PRODUCTION: dict[str, list[str]] = {
    "SPK-01 published version immutable": ["test_published_version_is_immutable"],
    "SPK-02 instance version'a sabit": ["test_instance_pinned_to_start_version"],
    "SPK-03 condition doğru+güvenli branch": [
        "test_boundary_values_select_correct_branch",
        "test_string_amount_rejected_not_executed",
    ],
    "SPK-04 sıralı onay sırası": ["test_deterministic_reload_completes"],
    "SPK-05 duplicate approval → tek karar": [
        "test_concurrent_duplicate_approval_single_winner",
        "test_sequential_retry_is_idempotent",
    ],
    "SPK-06 duplicate event → tek side effect": [
        "test_duplicate_event_produces_no_second_side_effect"
    ],
    "SPK-07 worker crash → kayıpsız": [
        "test_lease_recovery_after_worker_crash",
        "test_worker_run_once_processes_pending_events",
    ],
    "SPK-08 persisted timer tam bir kez": ["test_persisted_timer_fires_exactly_once"],
    "SPK-09 terminal instance guard": ["test_terminal_instance_rejects_late_decision"],
    "SPK-10 cross-tenant izolasyon": [
        "test_no_context_returns_zero_rows",
        "test_tenant_a_cannot_see_tenant_b_rows",
        "test_direct_uuid_guess_does_not_leak_existence",
    ],
    "SPK-11 state+outbox+event atomik": [
        "test_condition_error_rolls_back_whole_submit",
        "test_full_flow_atomic_writes",
    ],
    "SPK-12 concurrency conflict kontrollü": [
        "test_concurrent_form_submit_single_winner",
        "test_bounded_retry_then_failed_with_incident",
    ],
}


def _all_test_function_names() -> set[str]:
    names: set[str] = set()
    for directory in (INTEGRATION_DIR, UNIT_DIR):
        for path in directory.glob("test_*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    names.add(node.name)
    return names


def test_all_twelve_spike_criteria_are_covered() -> None:
    assert len(SPIKE_TO_PRODUCTION) == 12, "12 kriterin tamamı eşlenmelidir"
    existing = _all_test_function_names()
    missing: dict[str, list[str]] = {}
    for criterion, tests in SPIKE_TO_PRODUCTION.items():
        absent = [t for t in tests if t not in existing]
        if absent:
            missing[criterion] = absent
    assert not missing, f"eşlenen ama var olmayan production testleri: {missing}"


def test_no_production_import_of_spike_package() -> None:
    """Production kaynağı spikes.workflow-runtime'ı IMPORT ETMEZ (izolasyon)."""
    import flowpilot.modules.workflow_runtime as pkg

    root = Path(pkg.__file__).parent
    for py in root.rglob("*.py"):
        source = py.read_text(encoding="utf-8")
        assert "spike_runtime" not in source, f"production spike'a bağımlı: {py}"
        assert "spikes" not in source, f"production spike dizinine referans veriyor: {py}"
