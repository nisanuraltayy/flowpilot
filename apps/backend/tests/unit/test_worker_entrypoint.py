"""Worker entrypoint testleri.

`--check` gerçek worker döngüsünü başlatmaz; yalnız import ve ayar yüklemesini
doğrular. Network, Docker veya PostgreSQL GEREKTİRMEZ.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from flowpilot.worker.__main__ import (
    _DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
    _DEFAULT_POLL_INTERVAL_SECONDS,
    _HEARTBEAT_MAX_AGE_ENV_VAR,
    _HEARTBEAT_PATH_ENV_VAR,
    CHECK_OK_MESSAGE,
    HeartbeatError,
    IntervalError,
    _GracefulStop,
    _serve_loop,
    check_heartbeat,
    main,
    parse_tenant_allowlist,
    read_heartbeat_age,
    resolve_heartbeat_max_age,
    resolve_poll_interval,
    resolve_serve_tenants,
    write_heartbeat,
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
    assert (
        "one of the arguments --check --run-once --run --serve --check-heartbeat is required"
        in captured.err
    )
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


def test_serve_loop_uses_stable_order_every_sweep() -> None:
    """Sıra STABİL: her sweep ilk görülme sırasını kullanır (rotasyon YOK)."""
    seen: list[UUID] = []
    order = [UUID(_T1), UUID(_T2), UUID(_T3)]

    _serve_loop(
        tenant_ids=order,
        dispatch=seen.append,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=3,
    )

    assert seen[0:3] == order  # sweep 1: A, B, C
    assert seen[3:6] == order  # sweep 2: A, B, C
    assert seen[6:9] == order  # sweep 3: A, B, C


def test_serve_loop_order_follows_first_seen_after_dedupe() -> None:
    """Duplicate'ler deterministik biçimde kaldırılır ve sweep sırası bunu izler."""
    tenants = parse_tenant_allowlist([_T3, _T1, _T3, _T2, _T1])
    seen: list[UUID] = []

    _serve_loop(
        tenant_ids=tenants,
        dispatch=seen.append,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
    )

    assert tenants == [UUID(_T3), UUID(_T1), UUID(_T2)]
    assert seen == tenants * 2


def test_serve_loop_keeps_stable_order_despite_failing_tenant() -> None:
    """Hatalı tenant sırayı bozmaz ve SONRAKİ sweep'te aynı konumda yeniden denenir."""
    attempted: list[UUID] = []
    failing = UUID(_T2)

    def dispatch(tenant_id: UUID) -> None:
        attempted.append(tenant_id)
        if tenant_id == failing:
            raise RuntimeError("tenant dispatch exploded")

    _serve_loop(
        tenant_ids=[UUID(_T1), failing, UUID(_T3)],
        dispatch=dispatch,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
    )

    expected = [UUID(_T1), failing, UUID(_T3)]
    assert attempted[0:3] == expected  # hataya rağmen sonraki tenant aynı sırada
    assert attempted[3:6] == expected  # hatalı tenant aynı konumda yeniden denendi


def test_serve_loop_snapshots_tenant_list_for_the_sweep() -> None:
    """Sweep sırasında listenin sonradan değişmesi o sweep'i etkilemez."""
    tenants = [UUID(_T1), UUID(_T2)]
    seen: list[UUID] = []

    def dispatch(tenant_id: UUID) -> None:
        seen.append(tenant_id)
        tenants.append(UUID(_T3))  # çalışırken listeyi büyüt

    _serve_loop(
        tenant_ids=tenants,
        dispatch=dispatch,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
    )

    assert seen == [UUID(_T1), UUID(_T2), UUID(_T1), UUID(_T2)]


# --------------------------------------------------------- poll interval sözleşmesi


def test_interval_cli_overrides_environment() -> None:
    assert resolve_poll_interval(2.5, "7.5") == 2.5


def test_interval_falls_back_to_environment() -> None:
    assert resolve_poll_interval(None, "7.5") == 7.5


def test_interval_uses_default_when_cli_and_environment_absent() -> None:
    assert resolve_poll_interval(None, None) == _DEFAULT_POLL_INTERVAL_SECONDS
    assert resolve_poll_interval(None, "") == _DEFAULT_POLL_INTERVAL_SECONDS
    assert resolve_poll_interval(None, "   ") == _DEFAULT_POLL_INTERVAL_SECONDS


def test_interval_accepts_minimum_value() -> None:
    assert resolve_poll_interval(None, "0.1") == 0.1
    assert resolve_poll_interval(0.1, None) == 0.1


@pytest.mark.parametrize("raw", ["0", "-1", "-0.5", "0.09", "nan", "inf", "-inf", "abc", "1,5"])
def test_interval_rejects_invalid_environment_values(raw: str) -> None:
    with pytest.raises(IntervalError):
        resolve_poll_interval(None, raw)


@pytest.mark.parametrize("value", [0.0, -1.0, 0.09, float("nan"), float("inf")])
def test_interval_rejects_invalid_cli_values(value: float) -> None:
    with pytest.raises(IntervalError):
        resolve_poll_interval(value, None)


def test_interval_error_message_names_variable_without_leaking_value() -> None:
    """Mesaj yalnız değişken adı + kategori taşır; geçersiz değeri tekrar etmez."""
    with pytest.raises(IntervalError) as exc_info:
        resolve_poll_interval(None, "super-secret-typo-value")

    message = str(exc_info.value)
    assert "WORKER_POLL_INTERVAL_SECONDS" in message
    assert "super-secret-typo-value" not in message


def test_serve_rejects_invalid_interval_environment(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKER_POLL_INTERVAL_SECONDS", "0")
    with pytest.raises(SystemExit) as exc_info:
        main(["--serve", "--tenant", _T1])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "WORKER_POLL_INTERVAL_SECONDS" in captured.err
    assert "WORKER_TENANT_IDS" not in captured.err  # ilgisiz environment içeriği taşımaz


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


# --------------------------------------------------------------- heartbeat yazımı

_NOW = datetime(2026, 7, 24, 10, 0, 0, tzinfo=UTC)


def test_heartbeat_write_creates_utc_timestamp(tmp_path: Path) -> None:
    target = tmp_path / "beat"

    write_heartbeat(str(target), now=_NOW)

    stamped = datetime.fromisoformat(target.read_text(encoding="utf-8"))
    assert stamped == _NOW
    assert stamped.tzinfo is not None  # naive damga YASAK


def test_heartbeat_write_creates_missing_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "beat"

    write_heartbeat(str(target), now=_NOW)

    assert target.is_file()


def test_heartbeat_write_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    target = tmp_path / "beat"

    write_heartbeat(str(target), now=_NOW)

    # Atomik yazım: geçici dosya yer değiştirme sonrası KALMAZ (yarım okuma olmaz).
    assert [p.name for p in tmp_path.iterdir()] == ["beat"]


def test_heartbeat_write_overwrites_previous_stamp(tmp_path: Path) -> None:
    target = tmp_path / "beat"
    write_heartbeat(str(target), now=_NOW)

    later = _NOW + timedelta(seconds=30)
    write_heartbeat(str(target), now=later)

    assert datetime.fromisoformat(target.read_text(encoding="utf-8")) == later


def test_heartbeat_content_contains_only_timestamp(tmp_path: Path) -> None:
    """Heartbeat dosyası secret/tenant/PII TAŞIMAZ — yalnız zaman damgası."""
    target = tmp_path / "beat"

    write_heartbeat(str(target), now=_NOW)

    assert target.read_text(encoding="utf-8").strip() == _NOW.isoformat()


def test_heartbeat_age_is_measured_from_stamp(tmp_path: Path) -> None:
    target = tmp_path / "beat"
    write_heartbeat(str(target), now=_NOW)

    age = read_heartbeat_age(str(target), now=_NOW + timedelta(seconds=12))

    assert age == pytest.approx(12.0)


def test_heartbeat_age_rejects_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(HeartbeatError):
        read_heartbeat_age(str(tmp_path / "yok"), now=_NOW)


def test_heartbeat_age_rejects_corrupt_stamp(tmp_path: Path) -> None:
    target = tmp_path / "beat"
    target.write_text("not-a-timestamp", encoding="utf-8")

    with pytest.raises(HeartbeatError):
        read_heartbeat_age(str(target), now=_NOW)


# ------------------------------------------------------- heartbeat tazelik eşiği


def test_heartbeat_max_age_uses_default_when_absent() -> None:
    assert resolve_heartbeat_max_age(None) == _DEFAULT_HEARTBEAT_MAX_AGE_SECONDS
    assert resolve_heartbeat_max_age("  ") == _DEFAULT_HEARTBEAT_MAX_AGE_SECONDS


def test_heartbeat_max_age_reads_environment_value() -> None:
    assert resolve_heartbeat_max_age("15") == 15.0


@pytest.mark.parametrize("raw", ["abc", "0", "-1", "0.05", "nan", "inf"])
def test_heartbeat_max_age_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(HeartbeatError):
        resolve_heartbeat_max_age(raw)


def test_heartbeat_max_age_error_names_variable_without_leaking_value() -> None:
    with pytest.raises(HeartbeatError) as excinfo:
        resolve_heartbeat_max_age("gizli-deger")

    assert _HEARTBEAT_MAX_AGE_ENV_VAR in str(excinfo.value)
    assert "gizli-deger" not in str(excinfo.value)


# ------------------------------------------------------------ --check-heartbeat


def test_check_heartbeat_returns_zero_for_fresh_stamp(tmp_path: Path) -> None:
    target = tmp_path / "beat"
    write_heartbeat(str(target), now=_NOW)

    exit_code, message = check_heartbeat(
        str(target), max_age_seconds=60.0, now=_NOW + timedelta(seconds=10)
    )

    assert exit_code == 0
    assert "taze" in message


def test_check_heartbeat_returns_one_for_stale_stamp(tmp_path: Path) -> None:
    target = tmp_path / "beat"
    write_heartbeat(str(target), now=_NOW)

    exit_code, _ = check_heartbeat(
        str(target), max_age_seconds=60.0, now=_NOW + timedelta(seconds=61)
    )

    assert exit_code == 1


def test_check_heartbeat_accepts_age_exactly_at_threshold(tmp_path: Path) -> None:
    target = tmp_path / "beat"
    write_heartbeat(str(target), now=_NOW)

    exit_code, _ = check_heartbeat(
        str(target), max_age_seconds=60.0, now=_NOW + timedelta(seconds=60)
    )

    assert exit_code == 0


def test_check_heartbeat_returns_one_when_path_is_not_configured() -> None:
    """Yapılandırılmamış heartbeat sessizce 'sağlıklı' SAYILMAZ."""
    for path in (None, "", "   "):
        exit_code, message = check_heartbeat(path, max_age_seconds=60.0, now=_NOW)
        assert exit_code == 1
        assert _HEARTBEAT_PATH_ENV_VAR in message


def test_check_heartbeat_returns_one_when_file_is_missing(tmp_path: Path) -> None:
    exit_code, _ = check_heartbeat(str(tmp_path / "yok"), max_age_seconds=60.0, now=_NOW)

    assert exit_code == 1


def test_check_heartbeat_message_carries_no_secret(tmp_path: Path) -> None:
    target = tmp_path / "beat"
    write_heartbeat(str(target), now=_NOW)

    _, message = check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)

    assert "password" not in message.lower()
    assert "postgresql" not in message.lower()


def test_check_heartbeat_cli_mode_exits_one_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(_HEARTBEAT_PATH_ENV_VAR, raising=False)

    exit_code = main(["--check-heartbeat"])

    assert exit_code == 1
    assert _HEARTBEAT_PATH_ENV_VAR in capsys.readouterr().out


def test_check_heartbeat_cli_mode_exits_zero_for_fresh_stamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "beat"
    write_heartbeat(str(target), now=datetime.now(UTC))
    monkeypatch.setenv(_HEARTBEAT_PATH_ENV_VAR, str(target))
    monkeypatch.setenv(_HEARTBEAT_MAX_AGE_ENV_VAR, "60")

    assert main(["--check-heartbeat"]) == 0


def test_check_heartbeat_cli_mode_rejects_invalid_max_age(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(_HEARTBEAT_PATH_ENV_VAR, str(tmp_path / "beat"))
    monkeypatch.setenv(_HEARTBEAT_MAX_AGE_ENV_VAR, "-5")

    with pytest.raises(SystemExit) as excinfo:
        main(["--check-heartbeat"])

    assert excinfo.value.code == 2
    assert _HEARTBEAT_MAX_AGE_ENV_VAR in capsys.readouterr().err


def test_check_heartbeat_mode_is_mutually_exclusive_with_serve(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        main(["--check-heartbeat", "--serve", "--tenant", _T1])

    assert "not allowed with" in capsys.readouterr().err


# -------------------------------------------------- heartbeat servis loop entegrasyonu


def test_serve_loop_beats_before_first_sweep_and_after_each_cycle() -> None:
    beats: list[str] = []
    order: list[str] = []

    def dispatch(tenant_id: UUID) -> None:
        order.append("dispatch")

    def heartbeat() -> None:
        order.append("beat")
        beats.append("beat")

    _serve_loop(
        tenant_ids=[UUID(_T1), UUID(_T2)],
        dispatch=dispatch,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
        heartbeat=heartbeat,
    )

    # Süreç ayağa kalkar kalkmaz bir damga atılır (ilk sweep beklenmez),
    # sonra HER sweep sonunda bir damga daha atılır.
    assert order[0] == "beat"
    assert len(beats) == 3
    assert order == ["beat", "dispatch", "dispatch", "beat", "dispatch", "dispatch", "beat"]


def test_serve_loop_continues_when_heartbeat_write_fails() -> None:
    """Heartbeat yazımı BAŞARISIZ olsa bile dispatch DURMAZ."""
    processed: list[UUID] = []

    def heartbeat() -> None:
        raise OSError("disk dolu")

    cycles = _serve_loop(
        tenant_ids=[UUID(_T1), UUID(_T2)],
        dispatch=processed.append,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
        heartbeat=heartbeat,
    )

    assert cycles == 2
    assert len(processed) == 4


def test_serve_loop_runs_unchanged_when_heartbeat_is_not_configured() -> None:
    """Heartbeat opsiyoneldir: verilmezse döngü davranışı DEĞİŞMEZ."""
    processed: list[UUID] = []

    cycles = _serve_loop(
        tenant_ids=[UUID(_T1), UUID(_T2)],
        dispatch=processed.append,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
    )

    assert cycles == 2
    assert len(processed) == 4


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


def test_check_heartbeat_subprocess_exits_one_without_touching_database(
    tmp_path: Path,
) -> None:
    """Healthcheck komutu gerçekten çalışır, ASILI KALMAZ ve DB'ye DOKUNMAZ."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        _HEARTBEAT_PATH_ENV_VAR: str(tmp_path / "beat"),
        # Kasten GEÇERSİZ DSN: healthcheck DB'ye bağlanmaya çalışsaydı bu görünürdü.
        "DATABASE_URL": "postgresql+psycopg://invalid:invalid@127.0.0.1:1/none",
    }
    result = subprocess.run(
        [sys.executable, "-m", "flowpilot.worker", "--check-heartbeat"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=env,
    )

    assert result.returncode == 1, result.stderr
    assert _HEARTBEAT_PATH_ENV_VAR in result.stdout
    assert "Traceback" not in result.stderr
