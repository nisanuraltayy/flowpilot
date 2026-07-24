"""Worker entrypoint testleri.

`--check` gerçek worker döngüsünü başlatmaz; yalnız import ve ayar yüklemesini
doğrular. Network, Docker veya PostgreSQL GEREKTİRMEZ.
"""

from __future__ import annotations

import subprocess
import sys
from uuid import UUID

import pytest

from flowpilot.worker.__main__ import (
    CHECK_OK_MESSAGE,
    _GracefulStop,
    _serve_loop,
    main,
    parse_tenant_allowlist,
    resolve_serve_tenants,
)

_T1 = "00000000-0000-0000-0000-000000000001"
_T2 = "00000000-0000-0000-0000-000000000002"
_T3 = "00000000-0000-0000-0000-000000000003"


def test_check_returns_exit_code_zero(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--check"])

    assert exit_code == 0
    assert CHECK_OK_MESSAGE in capsys.readouterr().out


def test_check_reports_environment(capsys: pytest.CaptureFixture[str]) -> None:
    main(["--check"])

    out = capsys.readouterr().out
    assert "env=" in out
    assert "log_level=" in out


def test_unknown_argument_fails_in_controlled_way(capsys: pytest.CaptureFixture[str]) -> None:
    # Geçerli --check ile birlikte bilinmeyen argüman: argparse SystemExit(2) ile
    # çıkar, kullanım mesajı yazar ve worker loop BAŞLATMAZ.
    with pytest.raises(SystemExit) as exc_info:
        main(["--check", "--run-forever"])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "unrecognized arguments: --run-forever" in captured.err
    assert CHECK_OK_MESSAGE not in captured.out


def test_missing_mode_flag_fails_in_controlled_way(capsys: pytest.CaptureFixture[str]) -> None:
    # Mod seçilmeden çağrı kontrollü reddedilir
    # (--check / --run-once / --run / --serve birinden biri).
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "one of the arguments --check --run-once --run --serve is required" in captured.err
    assert CHECK_OK_MESSAGE not in captured.out


def test_modes_are_mutually_exclusive(capsys: pytest.CaptureFixture[str]) -> None:
    # --serve mevcut modlarla birlikte kullanılamaz.
    with pytest.raises(SystemExit) as exc_info:
        main(["--check", "--serve"])

    assert exc_info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_run_once_requires_tenant(capsys: pytest.CaptureFixture[str]) -> None:
    # --run-once --tenant olmadan: kontrollü hata, worker loop BAŞLATMAZ.
    with pytest.raises(SystemExit) as exc_info:
        main(["--run-once"])

    assert exc_info.value.code == 2
    assert "--tenant zorunludur" in capsys.readouterr().err


def test_run_rejects_unbounded_loop(capsys: pytest.CaptureFixture[str]) -> None:
    # Sonsuz busy loop YASAK: --run --max-passes 0 reddedilir.
    tenant = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(SystemExit) as exc_info:
        main(["--run", "--tenant", tenant, "--max-passes", "0"])

    assert exc_info.value.code == 2
    assert "sonsuz loop yasak" in capsys.readouterr().err


def test_run_rejects_multiple_tenants(capsys: pytest.CaptureFixture[str]) -> None:
    # Mevcut tek-tenant semantiği korunur: --run/--run-once çoklu tenant KABUL ETMEZ.
    with pytest.raises(SystemExit) as exc_info:
        main(["--run-once", "--tenant", _T1, "--tenant", _T2])

    assert exc_info.value.code == 2
    assert "tek --tenant kabul eder" in capsys.readouterr().err


# ------------------------------------------------------- --serve: CLI sözleşmesi


def test_serve_requires_at_least_one_tenant(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sessizce boş çalışan servis YASAK: tenant yoksa kontrollü hata.
    monkeypatch.delenv("WORKER_TENANT_IDS", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main(["--serve"])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "--serve için en az bir tenant gerekli" in captured.err
    assert "WORKER_TENANT_IDS" in captured.err


def test_serve_rejects_invalid_tenant_uuid(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WORKER_TENANT_IDS", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main(["--serve", "--tenant", "not-a-uuid"])

    assert exc_info.value.code == 2
    assert "geçerli UUID olmalıdır" in capsys.readouterr().err


# --------------------------------------------------- tenant allowlist çözümlemesi


def test_allowlist_parses_and_deduplicates_preserving_order() -> None:
    tenants = parse_tenant_allowlist([_T2, _T1, _T2, "  ", _T1])

    assert tenants == [UUID(_T2), UUID(_T1)]


def test_allowlist_rejects_invalid_uuid() -> None:
    with pytest.raises(ValueError):
        parse_tenant_allowlist(["not-a-uuid"])


def test_serve_tenants_prefer_cli_over_environment() -> None:
    # CLI ve environment BİRLEŞTİRİLMEZ; CLI verilmişse CLI geçerlidir.
    resolved = resolve_serve_tenants([_T1], f"{_T2},{_T3}")

    assert resolved == [UUID(_T1)]


def test_serve_tenants_fall_back_to_environment() -> None:
    resolved = resolve_serve_tenants(None, f" {_T1} , {_T2} ")

    assert resolved == [UUID(_T1), UUID(_T2)]


def test_serve_tenants_empty_environment_yields_empty_list() -> None:
    assert resolve_serve_tenants(None, "") == []
    assert resolve_serve_tenants(None, None) == []


# ------------------------------------------------------ adil döngü / hata izolasyonu


def test_serve_loop_processes_every_tenant_each_cycle() -> None:
    seen: list[UUID] = []
    stop = _GracefulStop()

    cycles = _serve_loop(
        tenant_ids=[UUID(_T1), UUID(_T2), UUID(_T3)],
        dispatch=seen.append,
        stop=stop,
        interval=0.0,
        max_cycles=2,
    )

    assert cycles == 2
    # Her tur her tenant TAM BİR KEZ işlenir (açlık yok).
    assert len(seen) == 6
    assert {seen.count(UUID(t)) for t in (_T1, _T2, _T3)} == {2}


def test_serve_loop_rotates_start_for_fairness() -> None:
    seen: list[UUID] = []
    _serve_loop(
        tenant_ids=[UUID(_T1), UUID(_T2), UUID(_T3)],
        dispatch=seen.append,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
    )

    # İkinci tur farklı tenant ile başlar → erken durdurmada hep aynı tenant öncelikli olmaz.
    assert seen[0] == UUID(_T1)
    assert seen[3] == UUID(_T2)


def test_serve_loop_isolates_failing_tenant() -> None:
    processed: list[UUID] = []
    failing = UUID(_T1)

    def dispatch(tenant_id: UUID) -> None:
        if tenant_id == failing:
            raise RuntimeError("tenant dispatch exploded")
        processed.append(tenant_id)

    cycles = _serve_loop(
        tenant_ids=[failing, UUID(_T2), UUID(_T3)],
        dispatch=dispatch,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
    )

    # Bir tenant sürekli hata verse bile döngü DEVAM eder ve diğerleri işlenir.
    assert cycles == 2
    assert processed.count(UUID(_T2)) == 2
    assert processed.count(UUID(_T3)) == 2


def test_serve_loop_stops_gracefully_between_tenants() -> None:
    stop = _GracefulStop()
    seen: list[UUID] = []

    def dispatch(tenant_id: UUID) -> None:
        seen.append(tenant_id)
        stop.request(15, None)  # ilk tenant'tan sonra durdurma iste

    cycles = _serve_loop(
        tenant_ids=[UUID(_T1), UUID(_T2), UUID(_T3)],
        dispatch=dispatch,
        stop=stop,
        interval=0.0,
        max_cycles=None,  # sınırsız: yalnız stop sinyaliyle biter
    )

    assert seen == [UUID(_T1)]  # durdurma isteği tur ortasında saygı görür
    assert cycles == 1


def test_serve_loop_with_no_tenants_does_nothing() -> None:
    assert (
        _serve_loop(tenant_ids=[], dispatch=lambda _: None, stop=_GracefulStop(), interval=0.0) == 0
    )


def test_module_entrypoint_runs_as_subprocess_and_exits_zero() -> None:
    # `python -m flowpilot.worker --check` gerçekten çalışır ve ASILI KALMAZ.
    result = subprocess.run(
        [sys.executable, "-m", "flowpilot.worker", "--check"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert CHECK_OK_MESSAGE in result.stdout
