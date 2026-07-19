"""Worker entrypoint testleri.

`--check` gerçek worker döngüsünü başlatmaz; yalnız import ve ayar yüklemesini
doğrular. Network, Docker veya PostgreSQL GEREKTİRMEZ.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from flowpilot.worker.__main__ import CHECK_OK_MESSAGE, main


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
    # Mod seçilmeden çağrı kontrollü reddedilir (--check / --run-once / --run birinden biri).
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "one of the arguments --check --run-once --run is required" in captured.err
    assert CHECK_OK_MESSAGE not in captured.out


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
